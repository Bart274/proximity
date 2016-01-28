"""
custom_components.proximity
~~~~~~~~~~~~~~~~~~~~~~~~~
Component to monitor the proximity of devices to a particular zone. The result is an entity created in HA which maintains the proximity data

Use configuration.yaml to enable the user to easily tune a number of settings:
- Zone: the zone which this component is measuring proximity to
- Override Zones: list of zones where, if a device is in, the device is omitted from proximity checking (useful for work or school)
- Devices: a list of devices to compare location against
- Tolerance: a measurement in meters where changes in location are omitted (used to filter small changes in GPS location)

Example configuration.yaml entry:
proximity:
  zone: home
  override_zones:
    - twork
    - elschool
  devices:
    - device_tracker.nwaring_nickmobile
    - device_tracker.eleanorsiphone
    - device_tracker.tsiphone
  tolerance: 50
  
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

#default tolerance
tolerance = 50

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
    if not('devices' in config[DOMAIN]):
        _LOGGER.error('devices not found in config')
        return False
    else:
        proximity_devices = []
        for variable in config[DOMAIN]['devices']:
            proximity_devices.append(variable)
            _LOGGER.info('Proximity device added: %s', variable)

    #get the direction of travel tolerance from configuration.yaml
    if 'tolerance' in config[DOMAIN]:
        tolerance = config[DOMAIN]['tolerance']
    _LOGGER.error('tolerance set to: %s', tolerance)

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

        entity_name = new_state.attributes['friendly_name']

        if not(old_state == None):
            _LOGGER.info('%s: old_state: %s', entity_name, old_state)
        else:
            _LOGGER.info('%s: no old_state', entity_name)
        
        if not(new_state == None):
            _LOGGER.info('%s: new_state: %s', entity_name, new_state)
        else:
            _LOGGER.info('%s: no new_state', entity_name)
            
        #default behaviour
        someone_is_home = False
        device_in_override_zone = False
        device_is_closest_to_home = False
        devices_compared = 0
        distance_from_zone = 0
        distance_travelled = 0
        direction_of_travel = 'not set'
        
        for device in proximity_devices:
            device_state = hass.states.get(device)
            if device_state.state == config[DOMAIN]['zone']:
                someone_is_home = True

        if new_state.state in override_zones:
            device_in_override_zone = True

        #noone appears to be home so we can continue to check if the device is the closest
        if someone_is_home == False:

            #reset the variables
            new_latitude = None
            new_longitude = None

            #pass first check, now check for latitude and longitude (on startup these values may not exist)
            if 'latitude' in new_state.attributes and 'longitude' in new_state.attributes:
                new_latitude = new_state.attributes['latitude']
                new_longitude = new_state.attributes['longitude']
                _LOGGER.info('%s: new co-ordintes: LAT %s: LONG: ', entity_name, new_latitude, new_longitude)
                
                #calculate the distance from home
                distance_from_zone = round(distance(proximity_latitude, proximity_longitude, new_latitude, new_longitude) / 1000, 1)
                _LOGGER.info('%s: distance from zone is: %s km', entity_name, distance_from_zone)

            #check whether the device is closest to home
            for device in proximity_devices:
                #ignore the device we're working on
                if device != entity:
                    #get the device state
                    device_state = hass.states.get(device)
                    if device_state not in override_zones:
                        #check that the distance from home can be calculated
                        if 'latitude' in device_state.attributes and 'longitude' in device_state.attributes:
                            #calculate the distance from home for the compare device
                            _LOGGER.info('%s: compare device %s: co-ordintes: LAT %s: LONG: %s', entity_name, device, device_state.attributes['latitude'], device_state.attributes['longitude'])
                            compare_distance_from_zone = round(distance(proximity_latitude, proximity_longitude, device_state.attributes['latitude'], device_state.attributes['longitude'])/1000 ,1)

                            #compare the distances from home
                            if distance_from_zone < compare_distance_from_zone:
                                device_is_closest_to_home = True
                                devices_compared = devices_compared + 1
                                _LOGGER.info('%s: closer than %s: %s compared with %s', entity_name, device, distance_from_zone, compare_distance_from_zone)
                            elif distance_from_zone > compare_distance_from_zone:
                                device_is_closest_to_home = False
                                devices_compared = devices_compared + 1
                                _LOGGER.info('%s: further away than %s: %s compared with %s', entity_name, device, distance_from_zone, compare_distance_from_zone)
                            else:
                                device_is_closest_to_home = False
                                devices_compared = devices_compared + 1                                          
                                _LOGGER.info('%s: same distance as %s: %s compared with %s', entity_name, device, distance_from_zone, compare_distance_from_zone)
                        else:
                            _LOGGER.info('%s: cannot compare with %s - no location attributes', entity_name, device)
                    else:
                        _LOGGER.info('%s: no need to compare with %s - device is in override zone', entity_name, device)
            
            #if the device is the closest to home continue to calculate direction of travel
            if device_is_closest_to_home == True or devices_compared == 0:
                #reset the variables
                old_latitude = None
                old_longitude = None

                #check we can calcualte the direction of travel (we need a previous state and a current LAT and LONG)
                if old_state != None and new_latitude != None and new_longitude != None:
                    #pass first check, now check that we have prevous LAT and LONG (on startup these values may not exist)
                    if 'latitude' in old_state.attributes and 'longitude' in old_state.attributes:
                        old_latitude = old_state.attributes['latitude']
                        old_longitude = old_state.attributes['longitude']
                        old_distance = distance(proximity_latitude, proximity_longitude, old_latitude, old_longitude)
                        _LOGGER.info('%s: old distance: %s', entity_name, old_distance)

                        new_distance = distance(proximity_latitude, proximity_longitude, new_latitude, new_longitude)
                        _LOGGER.info('%s: new distance from zone: %s', entity_name, new_distance)

                        distance_travelled = round(new_distance - old_distance,1)
                        _LOGGER.info('%s: distance travelled: %s', entity_name, distance_travelled)
                        
                        #check for a margin of error
                        if distance_travelled <= tolerance * -1:
                            direction_of_travel = 'towards'
                            _LOGGER.info('%s: device travelled %s metres: moving %s', entity_name, distance_travelled, direction_of_travel)
                        elif distance_travelled > tolerance:
                            direction_of_travel = 'away_from'
                            _LOGGER.info('%s: device travelled %s metres: moving %s', entity_name, distance_travelled, direction_of_travel)
                        else:
                            direction_of_travel = 'cannot_calculate'                                      
                            _LOGGER.info('%s: Cannot determine direction: %s is too small', entity_name, distance_travelled)
                    else:
                        _LOGGER.info('%s: Cannot determine direction of travel as previous LAT or LONG are missing', entity_name)
                        direction_of_travel = 'Unknown'
                else:
                    _LOGGER.info('%s: Cannot determine direction of travel as current LAT or LONG are missing', entity_name)
                    direction_of_travel = 'Unknown'
            else:
                _LOGGER.info('%s: complete - device is not closest to zone', entity_name)
        else:
            _LOGGER.info('%s: %s is occupied - nothing to see here', entity_name, proximity_zone)
            
        _LOGGER.info('%s: someone_is_home: %s', entity_name, someone_is_home)
        _LOGGER.info('%s: device_in_override_zone: %s', entity_name, device_in_override_zone)
        _LOGGER.info('%s: device_is_closest_to_home: %s', entity_name, device_is_closest_to_home)
        _LOGGER.info('%s: devices_compared: %s', entity_name, devices_compared)
        _LOGGER.info('%s: distance_from_zone: %s', entity_name, distance_from_zone)
        _LOGGER.info('%s: distance_travelled: %s', entity_name, distance_travelled)
        _LOGGER.info('%s: direction_of_travel: %s', entity_name, direction_of_travel)
            
        if someone_is_home:
            entity_attributes = {ATTR_DIST_FROM:0, ATTR_DIR_OF_TRAVEL:'arrived', ATTR_NEAREST_DEVICE:'not_applicable', ATTR_HIDDEN: False} 
            hass.states.set(ENTITY_ID, 0, entity_attributes)
            _LOGGER.info('%s Update entity: distance = 0: direction = arrived: device = not_applicable ', ENTITY_ID)
        elif not(someone_is_home) and not(device_in_override_zone)and devices_compared == 0:
            entity_attributes = {ATTR_DIST_FROM:distance_from_zone, ATTR_DIR_OF_TRAVEL:direction_of_travel, ATTR_NEAREST_DEVICE:entity_name, ATTR_HIDDEN: False} 
            hass.states.set(ENTITY_ID, distance_from_zone, entity_attributes)
            _LOGGER.info('%s Update entity: distance = %s: direction = %s: device = %s ', ENTITY_ID, distance_from_zone, direction_of_travel, entity_name)            
        elif device_is_closest_to_home:
            entity_attributes = {ATTR_DIST_FROM:distance_from_zone, ATTR_DIR_OF_TRAVEL:direction_of_travel, ATTR_NEAREST_DEVICE:entity_name, ATTR_HIDDEN: False} 
            hass.states.set(ENTITY_ID, distance_from_zone, entity_attributes)
            _LOGGER.info('%s Update entity: distance = %s: direction = %s: device = %s ', ENTITY_ID, distance_from_zone, direction_of_travel, entity_name)
        else:
            _LOGGER.info('%s Update entity: not updated', entity_name)
        
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
