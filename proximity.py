"""
custom_components.proximity
~~~~~~~~~~~~~~~~~~~~~~~~~
Component to monitor the proximity of devices to a particular zone. The result is an entity created in HA which maintains the proximity data

Use configuration.yaml to enable the user to easily tune a number of settings:
- Override States: where proximity is not calculated (e.g. work or school)
- Devices: a list of devices to compare location against to check closeness to home
- Default values to control the behavious of the thermostat

Example configuration.yaml entry:
proximity:
  zone: home
  override_states:
    - twork
    - elschool
  devices:
    - device_tracker.nwaring_nickmobile
    - device_tracker.eleanorsiphone
    - device_tracker.tsiphone
  tollerance: 50
  
"""

import logging
import re
from homeassistant.helpers.event import track_state_change
from homeassistant.helpers.entity import Entity
import homeassistant.util as util
from homeassistant.util.location import distance

from homeassistant.const import (ATTR_HIDDEN)

DEPENDENCIES = ['zone', 'device_tracker']

#domain for the component
DOMAIN = 'proximity'

#default tollerance
tollerance = 50

#default zone
proximity_zone = 'home'

#entity attributes
ATTR_DIST_FROM = 'dist_from_zone'
ATTR_DIR_OF_TRAVEL = 'dir_of_travel'
ATTR_NEAREST_DEVICE = 'nearest_device'

# Shortcut for the logger
_LOGGER = logging.getLogger(__name__)
    
def setup(hass, config):

    #get the zones and offsets from configuration.yaml
    override_zones = []
    if 'override_zones' in config[DOMAIN]:
        for variable in config[DOMAIN]['override_zones']:
            override_zones.append(variable)
            _LOGGER.info('Override zone loaded: %s', variable)

    #get the devices from configuration.yaml
    if 'devices' in config[DOMAIN]:
        proximity_devices = []
        for variable in config[DOMAIN]['devices']:
            proximity_devices.append(variable)
            _LOGGER.info('Proximity device added: %s', variable)
    else:
        _LOGGER.error('devices not found in config')
        return False

    #get the direction of travel tolerance from configuration.yaml
    if 'tollerance' in config[DOMAIN]:
        tollerance = config[DOMAIN]['tollerance']
    _LOGGER.error('Tollerance set to: %s', tollerance)

    #get the zone to monitor proximity to from configuration.yaml
    if 'zone' in config[DOMAIN]:
        proximity_zone  = config[DOMAIN]['zone']
    _LOGGER.error('Zone set to %s', proximity_zone)

    ENTITY_ID = DOMAIN + '.' + proximity_zone
    proximity_zone = 'zone.' + proximity_zone
    
    state = hass.states.get(proximity_zone)
    proximity_latitude = state.attributes.get('latitude')
    proximity_longitude = state.attributes.get('longitude')
    _LOGGER.info('Home settings: LAT:%s LONG:%s', proximity_latitude, proximity_longitude)

    #========================================================
    #create an entity so that the proximity values can be used for other components
    entities = set()
    
    #set the default values
    dist_from_home = 'not set'
    dir_of_travel = 'not set'
    nearest_device = 'not set'

    proximity = Proximity(hass, dist_from_home, dir_of_travel, nearest_device)
    proximity.entity_id = ENTITY_ID
    
    proximity.update_ha_state()
    entities.add(proximity.entity_id)
       
    #========================================================
     
    def check_proximity_dev_state_change(entity, old_state, new_state):
    
        #default behaviour
        someone_is_home = False
        update_proximity_entity = False
        entity_name = new_state.attributes['friendly_name']
        
        #initial check to see if the device is home
        if new_state.state != 'home':
            #check that the device is not in an override zone
            if new_state.state not in override_zones:
                #check whether another tracked device is home
                for device in proximity_devices:
                    if device != entity:
                        device_state = hass.states.get(device)
                        if device_state.state == 'home':
                            someone_is_home = True

                #noone appears to be home so we can continue to check if the device is the closest
                if someone_is_home == False:

                    #reset the variables
                    new_latitude = None
                    new_longitude = None
                    distance_from_zone = 0

                    #check we can calcualte the distance from home (we need the device to have a state and we also need to know where home is)
                    if new_state != None and proximity_latitude != None and proximity_longitude != None:
                        #pass first check, now check for latitude and longitude (on startup these values may not exist)
                        if 'latitude' in new_state.attributes and 'longitude' in new_state.attributes:
                            new_latitude = new_state.attributes['latitude']
                            new_longitude = new_state.attributes['longitude']
                            
                            #calculate the distance from home
                            distance_from_zone = round(distance(proximity_latitude, proximity_longitude, new_latitude, new_longitude) / 1000, 1)
                            _LOGGER.info('%s: distance from zone is: %s km', entity_name, distance_from_zone)

                            #set the default values before comparing with other devices
                            device_is_closest_to_home = False
                            devices_compared = 0

                            #check whether the device is closest to home
                            for device in proximity_devices:
                                #ignore the device we're working on
                                if device != entity:
                                    #get the device state
                                    device_state = hass.states.get(device)
                                    if device_state not in override_zones:
                                        #check that the distance from home can be calculated
                                        if 'latitude' in device_state.attributes and 'longitude' in device_state.attributes:
                                            #log that we have compared against one device
                                            devices_compared = devices_compared + 1
                                            #calculate the distance from home for the compare device
                                            compare_distance_from_zone = round(distance(proximity_latitude, proximity_longitude, device_state.attributes['latitude'], device_state.attributes['longitude'])/1000 ,1)
                                            #compare the distances from home
                                            if distance_from_zone <= compare_distance_from_zone:
                                                device_is_closest_to_home = True
                                                _LOGGER.info('%s: closer than %s: %s compared with %s', entity_name, device, distance_from_zone, compare_distance_from_zone)
                                            else:
                                                device_is_closest_to_home = False
                                                _LOGGER.info('%s: further away than %s: %s compared with %s', entity_name, device, distance_from_zone, compare_distance_from_zone)
                                        else:
                                            _LOGGER.warning('%s: cannot compare with %s - no location attributes', entity_name, device)
                                    else:
                                        _LOGGER.warning('%s: no need to compare with %s - device is in override zone', entity_name, device)
                                else:
                                    _LOGGER.warning('%s: no need to compare device with itself', entity_name)
                            
                            #if we've not been able to compare against any device then default that device is the closest to home
                            if devices_compared == 0:
                                device_is_closest_to_home = True
                                
                            #if the device is the closest to home continue to calculate direction of travel
                            if device_is_closest_to_home == True:
                                #reset the variables
                                old_latitude = None
                                old_longitude = None
                                distance_travelled = 0

                                #check we can calcualte the direction of travel (we need a previous state and a current LAT and LONG)
                                if old_state != None and new_latitude != None and new_longitude != None:
                                    #pass first check, now check that we have prevous LAT and LONG (on startup these values may not exist)
                                    if 'latitude' in old_state.attributes and 'longitude' in old_state.attributes:
                                        old_latitude = old_state.attributes['latitude']
                                        old_longitude = old_state.attributes['longitude']
                                        old_distance = distance(proximity_latitude, proximity_longitude, old_latitude, old_longitude)
                                        new_distance = distance(proximity_latitude, proximity_longitude, new_latitude, new_longitude)
                                        distance_travelled = round(new_distance - old_distance,1)
                                        
                                        #check for a margin of error
                                        if distance_travelled <= 0:
                                            direction_of_travel = 'towards'
                                            _LOGGER.info('%s: device travelled %s metres: moving %s', entity_name, distance_travelled, direction_of_travel)
                                        elif distance_travelled > 0:
                                            direction_of_travel = 'away_from'
                                            _LOGGER.info('%s: device travelled %s metres: moving %s', entity_name, distance_travelled, direction_of_travel)
                                        else:
                                            _LOGGER.info('%s: Cannot determine direction: %s is too small', entity_name, distance_travelled)
                                            
                                        # set the flag that we can update the proximity entitiy
                                        update_proximity_entity = True
                                        
                                    else:
                                        _LOGGER.warning('%s: Cannot determine direction of travel as previous LAT or LONG are missing', entity_name)
                                else:
                                    _LOGGER.warning('%s: Cannot determine direction of travel as current LAT or LONG are missing', entity_name)
                            else:
                                _LOGGER.info('%s: complete - device is not closest to zone', entity_name)
                        else:
                            _LOGGER.warning('%s: distance cannot be calculated - no LAT or LONG', entity_name)
                    else:
                        _LOGGER.warning('%s: distance cannot be calculated - device state is empty or zone LAT or LONG is blank', entity_name)
                else:
                    _LOGGER.info('%s: %s is occupied - nothing to see here', entity_name, proximity_zone)
            else:
                _LOGGER.info('%s: device is in override zone - nothing to see here', entity_name)           
        else:
            _LOGGER.info('%s: device is in proximity zone - nothing to see here', entity_name)
        
        if update_proximity_entity == True:
            #update the proximity entity values
            entity_attributes = {ATTR_DIST_FROM:distance_from_zone, ATTR_DIR_OF_TRAVEL: direction_of_travel, ATTR_NEAREST_DEVICE:entity_name, ATTR_HIDDEN: False} 
            hass.states.set(ENTITY_ID, distance_from_zone, entity_attributes)
            _LOGGER.info('%s Update entity: distance = %s: direction = %s: device = %s ', ENTITY_ID, distance_from_zone, direction_of_travel, entity_name)
        else:
            _LOGGER.info('%s: No Change to entity', ENTITY_ID)
        
    track_state_change(hass, proximity_devices, check_proximity_dev_state_change) 

    # Tells the bootstrapper that the component was successfully initialized
    return True

class Proximity(Entity):
    """ Represents a Proximity in Home Assistant. """
    # pylint: disable=too-many-arguments
    def __init__(self, hass, dist_from_home, dir_of_travel, nearest_device):
        self.hass = hass
        self._dist_from = dist_from_home
        self._dir_of_travel = dir_of_travel
        self._nearest_device = nearest_device

    def should_poll(self):
        return False

    @property
    def state(self):
        return self._dist_from
    
    @property
    def state_attributes(self):
        return {
            ATTR_DIST_FROM: self._dist_from,
            ATTR_DIR_OF_TRAVEL: self._dir_of_travel,
            ATTR_NEAREST_DEVICE: self._nearest_device,
            ATTR_HIDDEN: True,
        }
        return data

    @property
    def direction_of_travel(self):
        return self._dist_from

    @property
    def distance_from_zone(self):
        return self._dist_from
        
    @property
    def nearest_device(self):
        return self._dist_from