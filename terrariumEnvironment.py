# -*- coding: utf-8 -*-
import thread
import datetime
from threading import Timer
import copy
import time

from gevent import monkey, sleep
monkey.patch_all()

class terrariumEnvironment():

  def __init__(self, sensors, power_switches, door_sensor, weather, config):
    self.config = config
    self.sensors = sensors
    self.power_switches = power_switches

    self.door_sensor = door_sensor
    self.weather = weather
    self.reload_config()
    thread.start_new_thread(self.__engine_loop, ())

  def __parse_config(self):
    config = self.config.get_environment()

    self.light = config['light']
    if len(self.light) > 0:
      self.light['enabled'] = True if self.light['enabled'].lower() in ['true','on','1'] else False
      self.light['on'] = int(self.light['on'])
      self.light['off'] = int(self.light['off'])
      self.light['hours_shift'] = float(self.light['hours_shift'])
      self.light['min_hours'] = float(self.light['min_hours'])
      self.light['max_hours'] = float(self.light['max_hours'])
      self.light['power_switches'] = self.light['power_switches'].split(',')
    else:
      self.light['enabled'] = False

    self.sprayer = config['sprayer']
    if len(self.sprayer) > 0:
      self.sprayer['enabled'] = True if self.sprayer['enabled'].lower() in ['true','on','1'] else False
      self.sprayer['night_enabled'] = True if self.sprayer['night_enabled'].lower() in ['true','on','1'] else False
      self.sprayer['spray_duration'] = float(self.sprayer['spray_duration'])
      self.sprayer['spray_timeout'] = float(self.sprayer['spray_timeout'])
      self.sprayer['power_switches'] = self.sprayer['power_switches'].split(',')
      self.sprayer['sensors'] = self.sprayer['sensors'].split(',')
      self.sprayer['lastaction'] = datetime.datetime.now()
    else:
      self.sprayer['enabled'] = False

    self.heater = config['heater']
    if len(self.heater) > 0:
      self.heater['enabled'] =True if self.heater['enabled'].lower() in ['true','on','1'] else False
      self.heater['day_enabled'] = True if self.heater['day_enabled'].lower() in ['true','on','1'] else False
      self.heater['power_switches'] = self.heater['power_switches'].split(',')
      self.heater['sensors'] = self.heater['sensors'].split(',')
    else:
      self.heater['enabled'] = False

  def __set_config(self,part,data):
    for field in data:
      if 'light' == part:
        self.light[field] = data[field]
      elif 'sprayer' == part:
        self.sprayer[field] = data[field]
      elif 'heater' == part:
        self.heater[field] = data[field]

  def __engine_loop(self):
    while True:
      light = self.get_light_state()

      if light['enabled']:
        if light['on'] < int(time.time()) < light['off']:
          self.light_on()
        else:
          self.light_off()

      light = self.get_light_state()
      sprayer = self.get_sprayer_state()
      if sprayer['enabled'] and light['enabled']:
        if self.sprayer['night_enabled'] or light['state'] == 'on':
          if sprayer['alarm'] and self.door_sensor.is_closed():
            self.sprayer_on()

      heater = self.get_heater_state()
      if heater['enabled'] and light['enabled']:
        if self.heater['day_enabled'] or light['state'] == 'off':
          if heater['current'] < heater['alarm_min']:
            self.heater_on()
          elif heater['current'] > heater['alarm_max']:
            self.heater_off()
        else:
          self.heater_off()

      sleep(15)

  def __switch_on(self,part, state = None):
    is_on = True
    power_switches = []
    if 'light' == part:
      power_switches = self.light['power_switches']
    elif 'sprayer' == part:
      power_switches = self.sprayer['power_switches']
    elif 'heater' == part:
      power_switches = self.heater['power_switches']

    for switch in power_switches:
      if state is None:
        is_on = is_on and self.power_switches[switch].is_on()
      else:
        if state:
          self.power_switches[switch].on()
        else:
          self.power_switches[switch].off()

        is_on = state

    return is_on

  def __on(self,part):
    return True == self.__switch_on(part,True)

  def __off(self,part):
    return False == self.__switch_on(part,False)

  def __is_on(self,part):
    return self.__switch_on(part)

  def __is_off(self,part):
    return not self.__is_on(part)

  def get_config(self):
    return {'light' : self.get_light_config(),
            'sprayer' : self.get_sprayer_config() ,
            'heater' : self.get_heater_config()}

  def reload_config(self):
    self.__parse_config()

  def get_light_config(self):
    return self.light

  def set_light_config(self,data):
    self.__set_config('light',data)

  def light_on(self):
    return self.__on('light')

  def light_off(self):
    return self.__off('light')

  def is_light_on(self):
    return self.__is_on('light')

  def is_light_off(self):
    return self.__is_off('light')

  def get_light_state(self):
    now = datetime.datetime.now()
    if len(self.light) == 0:
      return {}

    data = {'on' : 0, 'off' : 0, 'modus' : self.light['modus'], 'enabled' : self.light['enabled']}
    if 'weather' == data['modus']:
      data['on'] = datetime.datetime.fromtimestamp(self.weather.get_data()['sun']['rise'])
      data['off'] = datetime.datetime.fromtimestamp(self.weather.get_data()['sun']['set'])

    elif 'timer' == data['modus']:
      data['on'] = self.light['on']
      data['off'] = self.light['off']

    # Duration check
    duration = data['off'] - data['on']
    # Reduce the amount of hours if to much
    if duration > datetime.timedelta(hours=self.light['max_hours']):
      duration -= datetime.timedelta(hours=self.light['max_hours'])
      data['on'] += datetime.timedelta(seconds=duration.total_seconds()/2)
      data['off'] -= datetime.timedelta(seconds=duration.total_seconds()/2)
    # Increase the amount of hours it to little
    elif duration < datetime.timedelta(hours=self.light['min_hours']):
      duration = datetime.timedelta(hours=self.light['min_hours']) - duration
      data['on'] -= datetime.timedelta(seconds=duration.total_seconds()/2)
      data['off'] += datetime.timedelta(seconds=duration.total_seconds()/2)

    # Shift hours
    data['on'] += datetime.timedelta(hours=self.light['hours_shift'])
    data['off'] += datetime.timedelta(hours=self.light['hours_shift'])

    # Shift time to next day?
    if now > data['off']:
      # Past offtime, so next day
      data['on'] += datetime.timedelta(hours=24)
      data['off'] += datetime.timedelta(hours=24)

    data['on'] = time.mktime(data['on'].timetuple())
    data['off'] = time.mktime(data['off'].timetuple())

    data['state'] = 'on' if self.is_light_on() else 'off'
    return data

  def get_sprayer_config(self):
    data = copy.deepcopy(self.sprayer)
    if 'lastaction' in data:
      del(data['lastaction'])
    return data

  def set_sprayer_config(self,data):
    self.__set_config('sprayer',data)

  def sprayer_on(self):
    if datetime.datetime.now() - self.sprayer['lastaction'] > datetime.timedelta(seconds=self.sprayer['spray_timeout']):
      self.__on('sprayer')
      (Timer(self.sprayer['spray_duration'], self.sprayer_off)).start()
      self.sprayer['lastaction'] = datetime.datetime.now()

  def sprayer_off(self):
    self.__off('sprayer')

  def is_sprayer_on(self):
    return self.__is_on('sprayer')

  def is_sprayer_off(self):
    return self.__is_off('sprayer')

  def get_sprayer_state(self):
    if len(self.sprayer) == 0:
      return {}

    amount = float(len(self.sprayer['sensors']))
    data = {'current' : sum(self.sensors[sensor].get_current() for sensor in self.sprayer['sensors']) / amount,
            'alarm_min' : sum(self.sensors[sensor].get_alarm_min() for sensor in self.sprayer['sensors']) / amount,
            'enabled' : self.sprayer['enabled']}

    light = self.get_light_state()
    data['alarm'] = (self.sprayer['night_enabled'] or (light['on'] < int(time.time()) < light['off'])) and data['current'] < data['alarm_min']
    data['state'] = 'on' if self.is_sprayer_on() else 'off'
    return data

  def get_heater_config(self):
    return self.heater

  def set_heater_config(self,data):
    self.__set_config('heater',data)

  def heater_on(self):
    self.__on('heater')

  def heater_off(self):
    self.__off('heater')

  def is_heater_on(self):
    return self.__is_on('heater')

  def is_heater_off(self):
    return self.__is_off('heater')

  def get_heater_state(self):
    if len(self.heater) == 0:
      return {}

    amount = float(len(self.heater['sensors']))
    data = {'current' : sum(self.sensors[sensor].get_current() for sensor in self.heater['sensors']) / amount,
          'alarm_min' : sum(self.sensors[sensor].get_alarm_min() for sensor in self.heater['sensors']) / amount,
          'alarm_max' : sum(self.sensors[sensor].get_alarm_max() for sensor in self.heater['sensors']) / amount,
          'modus' : self.heater['modus'],
          'day_enabled': self.heater['day_enabled'],
          'enabled' : self.heater['enabled']}

    light = self.get_light_state()
    data['alarm'] = (self.heater['day_enabled'] or not (light['on'] < int(time.time()) < light['off'])) and not (data['alarm_max'] >= data['current'] >= data['alarm_min'])
    data['state'] = 'on' if self.is_heater_on() else 'off'
    return data

  def get_average_temperature(self):
    return self.get_average('temperature')

  def get_average_humidity(self):
    return self.get_average('humidity')

  def get_average(self, type = None):
    average = {'temperature' : {'current': float(0), 'alarm_min' : float(0), 'alarm_max' : float(0), 'min' : float(0), 'max' : float(0), 'amount' : float(0), 'alarm' : False},
               'humidity'    : {'current': float(0), 'alarm_min' : float(0), 'alarm_max' : float(0), 'min' : float(0), 'max' : float(0), 'amount' : float(0), 'alarm' : False}}

    for sensorid in self.sensors:
      sensor = self.sensors[sensorid]
      sensor_type = sensor.get_type()
      average[sensor_type]['current'] += sensor.get_current()
      average[sensor_type]['alarm_min'] += sensor.get_alarm_min()
      average[sensor_type]['alarm_max'] += sensor.get_alarm_max()
      average[sensor_type]['min'] += sensor.get_min()
      average[sensor_type]['max'] += sensor.get_max()
      average[sensor_type]['amount'] += 1

    for sensortype in average:
      average[sensortype]['current'] /= average[sensortype]['amount']
      average[sensortype]['alarm_min'] /= average[sensortype]['amount']
      average[sensortype]['alarm_max'] /= average[sensortype]['amount']
      average[sensortype]['min'] /= average[sensortype]['amount']
      average[sensortype]['max'] /= average[sensortype]['amount']
      average[sensortype]['alarm'] = not average[sensortype]['alarm_min'] <  average[sensortype]['current'] < average[sensortype]['alarm_max']

      del(average[sensortype]['amount'])

    if type is not None and type in average:
      return { type : average[type] }

    return average
