
from PyQt4.QtGui import *
from PyQt4.QtCore import *


def newIcon(icon):
    return QIcon(':/' + icon)

def newButton(text, icon=None, slot=None):
    b = QPushButton(text)
    if icon is not None:
        b.setIcon(newIcon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b

def newAction(parent, text, slot=None, shortcut=None, icon=None,
        tip=None, checkable=False):
    """Create a new action and assign callbacks, shortcuts, etc."""
    a = QAction(text, parent)
    if icon is not None:
        a.setIcon(newIcon(icon))
    if shortcut is not None:
        a.setShortcut(shortcut)
    if tip is not None:
        a.setToolTip(tip)
        a.setStatusTip(tip)
    if slot is not None:
        a.triggered.connect(slot)
    if checkable:
        a.setCheckable(True)
    return a


def addActions(widget, actions):
    for action in actions:
        if action is None:
            widget.addSeparator()
        else:
            widget.addAction(action)

def labelValidator():
    return QRegExpValidator(QRegExp(r'^[^ \t].+'), None)

