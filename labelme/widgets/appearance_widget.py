from qtpy.QtCore import Qt
from qtpy.QtCore import Slot
from qtpy import QtGui
from qtpy import QtWidgets

from .. import utils


class AppearanceWidget(QtWidgets.QWidget):
  EVAL_PIXEL_ACCURACY = 0
  EVAL_MEAN_ACCURACY = 1
  EVAL_MEAN_IU = 2
  EVAL_FREQUENCY_WEIGHTED_IU = 3

  def __init__(self, callback):
    super(AppearanceWidget, self).__init__()
    self.slider_brightness = self._create_slider()
    self.slider_contrast = self._create_slider()

    resetBtn = QtWidgets.QPushButton(self.tr("Reset"))
    resetBtn.clicked.connect(self.onReset)

    showLayout = QtWidgets.QHBoxLayout()
    PixelmapCkb = QtWidgets.QCheckBox(self.tr("Show pixelmap"))
    PixelmapCkb.stateChanged.connect(lambda:self.onChangeShowPixelmal(PixelmapCkb))
    GroundTruthCkb = QtWidgets.QCheckBox(self.tr("Show groundtruth"))
    GroundTruthCkb.setChecked(True)
    GroundTruthCkb.stateChanged.connect(lambda:self.onChangeShowGT(GroundTruthCkb))
    showLayout.setContentsMargins(0, 0, 0, 0)
    showLayout.setSpacing(0)
    showLayout.addWidget(PixelmapCkb)
    showLayout.addWidget(GroundTruthCkb)

    splitter = QtWidgets.QFrame()
    splitter.setFrameShape(QtWidgets.QFrame.HLine)

    evalLabel = QtWidgets.QLabel(self.tr("Evaluation methods"))
    evalComb = QtWidgets.QComboBox()
    evalComb.addItems(["Pixel accuracy", "Mean accuracy", "Mean IU", "Frequency Weighted IU"])

    self.evalComb = evalComb
    evalLayout = QtWidgets.QHBoxLayout()
    evalLayout.setContentsMargins(0, 0, 0, 0)
    evalLayout.setSpacing(0)
    evalLayout.addWidget(evalLabel)
    evalLayout.addWidget(evalComb)

    formLayout = QtWidgets.QFormLayout()
    formLayout.addRow(self.tr("Brightness"), self.slider_brightness)
    formLayout.addRow(self.tr("Contrast"), self.slider_contrast)
    formLayout.addRow(resetBtn)
    formLayout.addRow(showLayout)

    formLayout.addRow(splitter)
    formLayout.addRow(evalLayout)

    self.setLayout(formLayout)
    self.callback = callback

    self.evalComponents = (
      GroundTruthCkb,
      evalLabel,
      evalComb,
    )
    
  def setAnnotations(self, annotations):
    self.annotations = annotations
  
  def setEnabled(self, bool):
    super(AppearanceWidget, self).setEnabled(bool)
    self.setEnabledEval(False)

  def setEnabledEval(self, bool):
    for comp in self.evalComponents:
      comp.setEnabled(bool)

  def _create_slider(self):
    slider = QtWidgets.QSlider(Qt.Horizontal)
    slider.setRange(0, 150)
    slider.setValue(50)
    slider.valueChanged.connect(self.onSliderValueChanged)
    return slider

  @Slot(int)
  def onSliderValueChanged(self, value):
    self.brightness = self.slider_brightness.value() / 50.0
    self.contrast = self.slider_contrast.value() / 50.0
    self.callback(brightness=self.brightness, contrast=self.contrast)

  @Slot()
  def onReset(self):
    self.slider_brightness.setValue(50)
    self.slider_contrast.setValue(50)

  @Slot("QCheckBox")
  def onChangeShowPixelmal(self, ckb):
    if ckb.isChecked():
      self.brightness = self.slider_brightness.value() / 50.0
      self.contrast = self.slider_contrast.value() / 50.0
      with utils.slot_disconnected(self.slider_brightness.valueChanged, self.onSliderValueChanged):
        self.slider_brightness.setValue(0)
      self.callback(show_pixelmap=True)
    else:
      with utils.slot_disconnected(self.slider_brightness.valueChanged, self.onSliderValueChanged):
        self.slider_brightness.setValue(self.brightness * 50.0)
      with utils.slot_disconnected(self.slider_contrast.valueChanged, self.onSliderValueChanged):
        self.slider_contrast.setValue(self.contrast * 50.0)
      self.callback(brightness=self.brightness, contrast=self.contrast, show_pixelmap=False)

  @Slot("QCheckBox")
  def onChangeShowGT(self, ckb):
    if ckb.isChecked():
      self.callback(show_groundtruth=True)
    else:
      self.callback(show_groundtruth=False)

