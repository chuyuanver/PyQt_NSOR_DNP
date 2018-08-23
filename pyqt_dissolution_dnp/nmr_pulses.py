'''
default unit is SI unit
'''
import numpy as np
from numpy import pi


class Delay:
    '''
    a delay class simulates the delay in the pulse sequence
    the waveform_generation method returns a 1d np array with zeros
    '''
    def __init__(self, duration,label):
        self.duration = duration
        self.label = label

    def waveform_generation(self, samp_freq, start_index, iteration):
        _d = len(self.duration)
        if _d == 2:
            return np.zeros(int(samp_freq*(self.duration[0]+iteration*self.duration[1])))
        elif _d == 1:
            return np.zeros(int(samp_freq*self.duration[0]))

    def nop(self, samp_freq, iteration):
        _d = len(self.duration)
        if _d == 2:
            return int(samp_freq*(self.duration[0]+iteration*self.duration[1]))
        elif _d == 1:
            return int(samp_freq*self.duration[0])


class Pulse(Delay):
    '''
    a pulse class simulates the pulse in the pulse sequence
    the waveform_generation method returns a 1d np array with specified properties
    iteration index is assumed to start with 0
    '''
    def __init__(self, duration, label, frequency,
                power, phase, shape = 'square'):
        super().__init__(duration,label)
        self.frequency = frequency
        self.power = power
        self.phase = phase

    def waveform_generation(self, samp_freq, start_index, iteration):
        _d = len(self.duration)
        _start_time = start_index/samp_freq
        if _d == 2:
            _data_points = int( (self.duration[0]+iteration*self.duration[1]) * samp_freq )
            _time_axis = np.linspace(_start_time, _start_time + (self.duration[0]+iteration*self.duration[1]), _data_points)
        if _d == 1:
            _data_points = int( self.duration[0] * samp_freq )
            _time_axis = np.linspace(_start_time, _start_time + self.duration[0], _data_points)
        _pw = len(self.power)
        _f = len(self.frequency)
        _ph = len(self.phase)
        return self.power[iteration % _pw] * np.cos( 2 * pi * self.frequency[iteration % _f]
                * _time_axis + self.phase[iteration % _ph] / 180 * pi)

    def shaped_waveform(self,waveform,samp_freq):
        pass


def pulse_repeat(pulse_sequence, repeat_num, repeat_pos):
    '''
    repeat the part in the pulse sequence that needs to be repeated
    '''
    new_sequence = pulse_sequence
    pos_adj = 0
    for num,pos in zip(repeat_num,repeat_pos):
        new_sequence[pos[1]+pos_adj:pos[1]+pos_adj] = pulse_sequence[ pos[0] : pos[1] ]*(num-1)
        pos_adj += (pos[1]-pos[0])*(num-1)
    return new_sequence


def convert_configuraton(config_str, const_dict):
    '''
    convert the configuration part of the pulse, only do one thing, that is
    convert each line into a pulse sequence without considering the repeat
    '''

    seperated_str = config_str.split(' ')
    label = int(seperated_str[0])
    identity = seperated_str[1]
    duration = const_dict[identity]
    if identity[0] == 'd':
        return Delay(duration, label)
    elif identity[0] == 'p':
        phase = seperated_str[4]
        power = seperated_str[3]
        freq = seperated_str[2]
        return Pulse(duration, label, const_dict[freq], const_dict[power], const_dict[phase])


def dict_create(line):
    dict_key = line.split('=')[0].strip()
    if dict_key == 'repeat_num' or dict_key == 'repeat_pos':
        dict_val = list(map(lambda val: int(val), line.split('=')[1].strip().split(' ')))
    else:
        dict_val = list(map(lambda val: float(val), line.split('=')[1].strip().split(' ')))
    if dict_key == 'repeat_pos':
        dict_val = list(zip(dict_val[0::2],dict_val[1::2]))
    return {dict_key:dict_val}


def pulse_interpreter(file_path, samp_freq, iteration):
    '''
    interpret the pulse file into np array
    '''

    with open(file_path,'r') as fl:
        constant_part = False
        configuration_part = False
        pulse_sequence = []
        const_dict = {}
        for line in fl:
            _line = line.strip()
            if line[0] == '#' or _line == '':
                continue

            elif _line == 'constant:':
                constant_part = True
                continue

            elif _line == 'configuration:':
                configuration_part = True
                constant_part = False
                continue

            elif constant_part:
                const_dict.update(dict_create(_line))

            elif configuration_part:
                if len(_line.split(' ')) > 1:
                    pulse_sequence.append(convert_configuraton( _line, const_dict))

    repeat_num = const_dict['repeat_num']
    repeat_pos = const_dict['repeat_pos']
    if repeat_num[0] > 1 and repeat_pos[0] != (0,0) and len(repeat_num) == len(repeat_pos):
            pulse_sequence = pulse_repeat(pulse_sequence, repeat_num, repeat_pos)

    current_index = 0
    final_pulse = np.array([])

    for item in pulse_sequence:
        current_wave = item.waveform_generation(samp_freq, current_index,iteration)
        current_index += item.nop(samp_freq,iteration)
        final_pulse = np.concatenate((final_pulse,current_wave),axis = 0)
    return final_pulse
