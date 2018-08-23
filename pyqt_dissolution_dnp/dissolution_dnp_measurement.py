from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

import pyqtgraph as pg

from matplotlib.backends.qt_compat import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import (
        FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure
import matplotlib

from nidaqmx.task import Task
from nidaqmx import constants

import sys
import os

import numpy as np
from numpy import pi

import json

import time

BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

PARAMETER_FILE = BASE_FOLDER + r'\pyqt_dissolution_dnp\parameter.txt'
'''
################################################################################
useful functions
'''

def read_parameter(parameter_file):
    with open(parameter_file, 'r') as f:
        parameter_raw = f.read()
    parameters = json.loads(parameter_raw)
    return parameters

def save_parameter(parameter_file, **kwargs):
    parameters = read_parameter(parameter_file)
    with open(parameter_file,'w') as f:
        for key,val in kwargs.items():
            parameters[key] = val
        json.dump(parameters, f, indent = 2)

'''
################################################################################
Multithreading
'''
class WorkerSignals(QObject):
    detector_triggered = pyqtSignal()
    data = pyqtSignal(np.ndarray)


'''
--------------------------fluid detector read-----------------------------------
'''

class FluidDetectorReadWorker(QRunnable): #Multithreading
    def __init__(self, task_handle, data, ready_handle, stop_handle):
        super(FluidDetectorReadWorker,self).__init__()
        self.di_task = task_handle
        self.data = data
        self.signals = WorkerSignals()
        self.ready = ready_handle
        self.stop = stop_handle

    @pyqtSlot()
    def run(self):
        self.di_task.start()
        dt = 0
        n = 0
        while True:
            t0 = time.time()
            # self.data = np.append(self.data,self.di_task.read())
            if not self.ready.isChecked():
                self.data = np.roll(self.data,1)
                self.signals.data.emit(self.data)
            self.data[0] = self.di_task.read()
            # self.curve.setData(y = self.data)

            if (self.ready.isChecked() and self.data[0] == 0) or self.stop.isChecked():
                self.signals.detector_triggered.emit()
                break
            # time.sleep(0.0005)

            t1 = time.time()
            dt = (dt*n + (t1-t0))/(n+1)
            n += 1

        self.di_task.stop()



'''
--------------------------fluid detector calibrate------------------------------
'''

class CalibrateFluidDetectorWorker(QRunnable):
    def __init__(self, task_handle):
        super(CalibrateFluidDetectorWorker,self).__init__()
        self.calibrate_task = task_handle

    @pyqtSlot()
    def run(self):
        self.calibrate_task.write(33) #100010
        time.sleep(0.1)
        self.calibrate_task.write(2)  #000010



'''
--------------------------valve switch------------------------------------------
'''

class SwitchValveWorker(QRunnable):
    def __init__(self,task_handle,state):
        super(SwitchValveWorker,self).__init__()
        self.state = state
        self.switch_task = task_handle

    @pyqtSlot()
    def run(self):
        if self.state == 'load':
            self.switch_task.write(2) #000010
        elif self.state == 'inject':
            self.switch_task.write(1) #000001
        time.sleep(0.5)

class DataRecorderWorker(QRunnable):
    def __init__(self,task_handle,inj_time):
        super(DataRecorderWorker,self).__init__()
        self.task_handle = task_handle
        self.inj_time = inj_time

    @pyqtSlot()
    def run(self):
        '''
        inject
        '''
        self.task_handle.write(1) #000001

        '''
        wait
        '''
        time.sleep(self.inj_time)

        '''
        switch back
        '''
        self.task_handle.write(2) #000010

        time.sleep(0.5)
        print('record data')
        '''
        reserved for daq acquisition
        '''


'''
################################################################################
customized widget
'''
class MyLineEdit(QLineEdit):
    '''
    edit class for capturing input
    '''
    textModified = pyqtSignal(str,str) # (key, text)
    def __init__(self, key, contents='', parent=None):
        super(MyLineEdit, self).__init__(contents, parent)
        self.key = key
        self.editingFinished.connect(self.checkText)
        self.textChanged.connect(lambda: self.checkText())
        self.returnPressed.connect(lambda: self.checkText(True))
        self._before = contents

    def checkText(self, _return=False):
        if (not self.hasFocus() or _return):
            self._before = self.text()
            self.textModified.emit(self.key, self.text())

'''
################################################################################
main gui window intitation
'''
class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow,self).__init__()

        self.setWindowTitle('Dissolution DNP Measurement (NSOR project)')
        self.setWindowIcon(QIcon(BASE_FOLDER + r"\pyqt_analysis\icons\window_icon.png"))

        '''
        --------------------------setting menubar-------------------------------
        '''
        mainMenu = self.menuBar() #create a menuBar
        fileMenu = mainMenu.addMenu('&File') #add a submenu to the menu bar

        '''
        --------------------------setting toolbar-------------------------------
        '''
        self.toolbar = self.addToolBar('nsor_toolbar') #add a tool bar to the window
        self.toolbar.setIconSize(QSize(100,100))

        self.statusBar() #create a status bar


        '''
        --------------------------setting matplotlib----------------------------
        axes are contained in one dictionary
        ax['time']
        ax['freq']
        also initiate the vertical lines
        vline['time_l']
        vline['time_r']
        vline['freq_l']
        vline['freq_r']
        '''
        if app.desktop().screenGeometry().height() == 2160:
            matplotlib.rcParams.update({'font.size': 28})
        elif app.desktop().screenGeometry().height() == 1080:
            matplotlib.rcParams.update({'font.size': 14})
        canvas = FigureCanvas(Figure(figsize=(50, 15)))

        self.ax = {}
        self.vline = {}
        self.ax['nmr_time'] = canvas.figure.add_subplot(221)
        self.ax['nmr_freq'] = canvas.figure.add_subplot(222)
        self.ax['nsor_time'] = canvas.figure.add_subplot(223)
        self.ax['nsor_freq'] = canvas.figure.add_subplot(224)

        for axis in self.ax.values():
            if app.desktop().screenGeometry().height() == 2160:
                axis.tick_params(pad=20)
            elif app.desktop().screenGeometry().height() == 1080:
                axis.tick_params(pad=10)
        '''
        use pyqtgraph for optical detector because of the fast drawing speed
        '''
        self.optical_graph = pg.PlotWidget()
        self.optical_data = np.zeros(500)
        self.optical_data += 1
        self.optical_curve = self.optical_graph.plot(self.optical_data)
        self.optical_graph.setYRange(-0.1,1.1)
        print(self.optical_graph.size)


        '''
        --------------------------setting widgets-------------------------------
        '''
        exitProgram = QAction(QIcon(BASE_FOLDER + r'\pyqt_analysis\icons\exit_program.png'),'&Exit',self)
        exitProgram.setShortcut("Ctrl+W")
        exitProgram.setStatusTip('Close the Program')
        exitProgram.triggered.connect(self.exit_program)
        fileMenu.addAction(exitProgram)

        editParameters = QAction('&Edit Parameter', self)
        editParameters.setShortcut('Ctrl+E')
        editParameters.setStatusTip('open and edit the parameter file')
        editParameters.triggered.connect(self.edit_parameters)

        saveParameters = QAction('&Save Parameter', self)
        saveParameters.setShortcut('Ctrl+S')
        saveParameters.setStatusTip('save the parameters on screen to file')
        saveParameters.triggered.connect(self.save_parameters)
        parameterMenu = mainMenu.addMenu('&Parameter')
        parameterMenu.addAction(editParameters)
        parameterMenu.addAction(saveParameters)

        startExpBtn = QPushButton('START',self)
        startExpBtn.clicked.connect(self.fluid_detector_read)
        calibrateBtn = QPushButton('CALIBRATE',self)
        calibrateBtn.clicked.connect(self.calibrate_fluid_detector)
        self.readyBtn = QRadioButton('READY',self)
        self.stopBtn = QPushButton('STOP',self)
        self.stopBtn.setCheckable(True)

        injBtn = QPushButton('INJECT', self)
        injBtn.clicked.connect(lambda: self.switch_mode('inject'))
        loadBtn = QPushButton('LOAD', self)
        loadBtn.clicked.connect(lambda: self.switch_mode('load'))

        '''
        --------------------------setting layout/mix widget set-----------------
        '''
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setTabPosition(QTabWidget.North)
        tabs.setMovable(True)

        tab = {'parameter': QWidget(), 'data': QWidget()}
        tab_layout = {'parameter' : QVBoxLayout(), 'data': QHBoxLayout()}
        parameter_tab_layout = QFormLayout()
        sub_tab_layout = {'time': QVBoxLayout(), 'freq':QVBoxLayout()}
        optical_layout = QHBoxLayout()

        '''
        importing edits from paramter
        '''
        self.edits = {}
        self.parameters = read_parameter(PARAMETER_FILE)
        for key,value in self.parameters.items():
            if type(value) == list:
                value = str(value[0])+' '+str(value[1])
            self.edits[key] = MyLineEdit(key, value, self)
            self.edits[key].setStatusTip(f'{key}')
            if 'nmr' in key:
                key_str = 'NMR Channel'
            elif 'nsor' in key:
                key_str = 'NSOR Channel'
            else:
                key_str = key.replace('_', ' ').title()

            if not ('time' in key or 'freq' in key):
                '''
                parameter tab layout:
                file_name; pulse_file; samp_rate; iteration; average; pulse_chan;
                nmr_chan; nsor_chan; laser_chan
                '''
                layout_temp = QHBoxLayout()
                layout_temp.addWidget(self.edits[key])
                if 'file' in key:
                    self.edits[key].setFixedWidth(1250)
                else:
                    layout_temp.addStretch(1)

                parameter_tab_layout.addRow(key_str,layout_temp)

            else:
                '''
                data tab layout:
                time_x_limit; time_y_limit; freq_x_limit; freq_y_limit;
                time_cursor; freq_cursor
                '''
                sub_tab_layout[key[0:4]].addWidget(QLabel(key_str,self))
                sub_tab_layout[key[0:4]].addWidget(self.edits[key])
                if 'freq' in key:
                    self.edits[key].setFixedWidth(250)

        for key in sub_tab_layout.keys():
            sub_tab_layout[key].addStretch(1)

        tab_layout['parameter'].addLayout(parameter_tab_layout)
        tab_layout['parameter'].addLayout(optical_layout)


        button_layout = QVBoxLayout()
        button_layout.addWidget(injBtn)
        button_layout.addWidget(loadBtn)
        button_layout.addWidget(startExpBtn)
        button_layout.addWidget(self.stopBtn)
        button_layout.addWidget(calibrateBtn)
        button_layout.addWidget(self.readyBtn)

        button_layout.addStretch(1)

        optical_layout.addLayout(button_layout)
        optical_layout.addWidget(self.optical_graph)


        # tab_layout['parameter'].addStretch(1)
        tab_layout['data'].addLayout(sub_tab_layout['time'])
        tab_layout['data'].addWidget(canvas)
        tab_layout['data'].addLayout(sub_tab_layout['freq'])
        for key in tab.keys():
            tabs.addTab(tab[key], key)
            tab[key].setLayout(tab_layout[key])


        _main = QWidget()
        self.setCentralWidget(_main)
        layout1 = QVBoxLayout(_main)
        layout1.addWidget(tabs)


        '''
        --------------------------Multithreading preparation--------------------
        '''
        self.threadpool = QThreadPool() #Multithreading

        '''
        --------------------------Daqmx Task initialization---------------------
        '''
        di_line = 'Dev1/port2/line2'
        self.di_task = Task('di_task')
        self.di_task.di_channels.add_di_chan(di_line)

        do_line = 'Dev1/port1/line0, Dev1/port1/line1, Dev1/port1/line5'
        self.do_task = Task('do_task')
        self.do_task.do_channels.add_do_chan(do_line)
        self.do_task.start()

        '''
        -------------------------Menu bar slot----------------------------------
        '''
    def edit_parameters(self):
        os.startfile(PARAMETER_FILE)

    def save_parameters(self):
        for key in self.parameters.keys():
            str = self.edits[key].text()
            if 'freq' in key or 'time' in key:
                self.parameters[key] = str.split(' ')
            else:
                self.parameters[key] = str

        save_parameter(PARAMETER_FILE, **self.parameters)

    def exit_program(self):
        choice = QMessageBox.question(self, 'Exiting',
                                                'Are you sure about exit?',
                                                QMessageBox.Yes | QMessageBox.No) #Set a QMessageBox when called
        if choice == QMessageBox.Yes:  # give actions when answered the question
            self.do_task.stop()
            self.di_task.stop()
            self.do_task.close()
            self.di_task.close()
            sys.exit()


        '''
        -------------------------button slots-----------------------------------
        '''

    def switch_mode(self, mode):
        worker = SwitchValveWorker(self.do_task, mode)
        self.threadpool.start(worker)

        '''
        --------------------------Multithreading slots--------------------------
        '''
    def fluid_detector_read(self):
        worker = FluidDetectorReadWorker(self.di_task, self.optical_data, self.readyBtn, self.stopBtn)
        worker.signals.detector_triggered.connect(self.collect_data)
        worker.signals.data.connect(self.update_optical_curve)
        self.threadpool.start(worker)

    def update_optical_curve(self,data):
        self.optical_curve.setData(data)

    def collect_data(self):
        if self.stopBtn.isChecked():
            self.stopBtn.toggle()
        else:
            print('collecting data')
            # injection time
            inj_time = int(self.edits['injection_delay'].text())
            worker = DataRecorderWorker(self.do_task, inj_time)
            self.threadpool.start(worker)

        # self.optical_graph.clear()

    def calibrate_fluid_detector(self):
        worker = CalibrateFluidDetectorWorker(self.do_task)
        self.threadpool.start(worker)

'''
################################################################################
'''

app = QApplication(sys.argv)

window = MainWindow()
window.move(300,300)
window.show()
app.exec_()
