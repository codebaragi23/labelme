from qtpy.QtCore import Qt
from qtpy.QtCore import Slot
from qtpy import QtGui
from qtpy import QtWidgets

from .. import utils


class AppearanceWidget(QtWidgets.QWidget):
  EVAL_PIXEL_ACCURACY = 0
  EVAL_MEAN_ACCURACY = 1
  EVAL_MEAN_IOU = 2
  EVAL_FREQUENCY_WEIGHTED_IOU = 3

  def __init__(self, callback):
    super(AppearanceWidget, self).__init__()
    self.slider_brightness = self._create_slider()
    self.slider_contrast = self._create_slider()

    resetBtn = QtWidgets.QPushButton(self.tr("Reset"))
    resetBtn.clicked.connect(self.onReset)

    showLayout = QtWidgets.QHBoxLayout()
    PixelmapCkb = QtWidgets.QCheckBox(self.tr("Show pixelmap"))
    PixelmapCkb.stateChanged.connect(lambda:self.onChangeShowPixelmal(PixelmapCkb))
    showLayout.setContentsMargins(0, 0, 0, 0)
    showLayout.setSpacing(0)
    showLayout.addWidget(PixelmapCkb)

    formLayout = QtWidgets.QFormLayout()
    formLayout.addRow(self.tr("Brightness"), self.slider_brightness)
    formLayout.addRow(self.tr("Contrast"), self.slider_contrast)
    formLayout.addRow(resetBtn)
    formLayout.addRow(showLayout)

    self.setLayout(formLayout)
    self.callback = callback
    
  def setAnnotations(self, annotations):
    self.annotations = annotations
  
  def setEnabled(self, bool):
    super(AppearanceWidget, self).setEnabled(bool)

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
