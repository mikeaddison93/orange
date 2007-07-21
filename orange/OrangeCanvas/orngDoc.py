# Author: Gregor Leban (gregor.leban@fri.uni-lj.si)
# Description:
#    document class - main operations (save, load, ...)
#
import sys, os, os.path, string, traceback
from qt import *
from qtcanvas import *
from xml.dom.minidom import Document, parse
import orngView
import orngCanvasItems
import orngTabs
from orngDlgs import *
from orngSignalManager import SignalManager
import cPickle

class SchemaDoc(QMainWindow):
    def __init__(self, canvasDlg, *args):
        apply(QMainWindow.__init__,(self,) + args)
        self.canvasDlg = canvasDlg
        self.canSave = 0
        self.resize(700,500)
        self.showNormal()
        self.setCaption("Schema"+" " + str(self.canvasDlg.iDocIndex))
        self.canvasDlg.iDocIndex = self.canvasDlg.iDocIndex + 1

        self.enableSave(False)
        self.setIcon(QPixmap(canvasDlg.file_new))
        self.lines = []                         # list of orngCanvasItems.CanvasLine items
        self.widgets = []                       # list of orngCanvasItems.CanvasWidget items
        self.signalManager = SignalManager()    # signal manager to correctly process signals
        self.ctrlPressed = 0

        self.documentpath = canvasDlg.settings["saveSchemaDir"]
        self.documentname = str(self.caption())
        self.applicationpath = canvasDlg.settings["saveApplicationDir"]
        self.applicationname = str(self.caption())
        self.documentnameValid = False
        self.loadedSettingsDict = {}
        self.canvas = QCanvas(2000,2000)
        self.canvasView = orngView.SchemaView(self, self.canvas, self)
        self.setCentralWidget(self.canvasView)
        self.canvasView.show()


    # we are about to close document
    # ask user if he is sure
    def closeEvent(self,ce):
        newSettings = self.loadedSettingsDict and self.loadedSettingsDict != dict([(widget.caption, widget.instance.saveSettingsStr()) for widget in self.widgets])
        self.canSave = self.canSave or newSettings

        self.synchronizeContexts()
        if self.canvasDlg.settings["autoSaveSchemasOnClose"] and self.widgets != []:
            self.save(os.path.join(self.canvasDlg.outputDir, "_lastSchema.ows"))

        if not self.canSave or self.canvasDlg.settings["dontAskBeforeClose"]:
            if newSettings:
                self.saveDocument()
            self.clear()
            ce.accept()
            QMainWindow.closeEvent(self, ce)
            return

        #QMainWindow.closeEvent(self, ce)
        res = QMessageBox.information(self,'Orange Canvas','Do you want to save changes made to schema?','&Yes','&No','&Cancel',0)
        if res == 0:
            self.saveDocument()
            ce.accept()
            self.clear()
        elif res == 1:
            self.clear()
            ce.accept()
        else:
            ce.ignore()
            return
        QMainWindow.closeEvent(self, ce)

    def enableSave(self, enable):
        self.canSave = enable
        self.canvasDlg.enableSave(enable)

    def focusInEvent(self, ev):
        self.canvasDlg.enableSave(self.canSave)

    # called to properly close all widget contexts
    def synchronizeContexts(self):
        for widget in self.widgets[::-1]:
            widget.instance.synchronizeContexts()

    # add line connecting widgets outWidget and inWidget
    # if necessary ask which signals to connect
    def addLine(self, outWidget, inWidget, enabled = True):
        # check if line already exists
        line = self.getLine(outWidget, inWidget)
        if line:
            self.resetActiveSignals(outWidget, inWidget, None, enabled)
            return

        if self.signalManager.existsPath(inWidget.instance, outWidget.instance):
            QMessageBox.critical( None, "Orange Canvas", "Cyclic connections are not allowed in Orange Canvas.", QMessageBox.Ok + QMessageBox.Default )
            return

        dialog = SignalDialog(self.canvasDlg, None, "", True)
        dialog.setOutInWidgets(outWidget, inWidget)
        connectStatus = dialog.addDefaultLinks()
        if connectStatus == -1:
            self.canvasDlg.menuItemRebuildWidgetRegistry()
            for widget in self.widgets: widget.updateTooltip()
            for (outName, inName) in dialog._links: dialog.removeLink(outName, inName)
            dialog.setOutInWidgets(outWidget, inWidget)
            connectStatus = dialog.addDefaultLinks()

        if connectStatus == 0:
            QMessageBox.information( None, "Orange Canvas", "Selected widgets don't share a common signal type. Unable to connect.", QMessageBox.Ok + QMessageBox.Default )
            return
        elif connectStatus == -1:
            QMessageBox.critical( None, "Orange Canvas", "Error while connecting widgets. Please rebuild  widget registry (menu Options/Rebuild widget registry) and restart Orange Canvas. Some of the widgets have now different signals.", QMessageBox.Ok + QMessageBox.Default )
            return

        # if there are multiple choices, how to connect this two widget, then show the dialog
        if self.ctrlPressed or len(dialog.getLinks()) > 1 or dialog.multiplePossibleConnections or dialog.allSignalsTaken or dialog.getLinks() == []:
            res = dialog.exec_loop()
            if dialog.result() == QDialog.Rejected:
                return

        self.signalManager.setFreeze(1)
        linkCount = 0
        for (outName, inName) in dialog.getLinks():
            linkCount += self.addLink(outWidget, inWidget, outName, inName, enabled)

        self.signalManager.setFreeze(0, outWidget.instance)

        # if signals were set correctly create the line, update widget tooltips and show the line
        line = self.getLine(outWidget, inWidget)
        if line:
            outWidget.updateTooltip()
            inWidget.updateTooltip()

        self.enableSave(True)
        return line

    # ####################################
    # reset signals of an already created line
    def resetActiveSignals(self, outWidget, inWidget, newSignals = None, enabled = 1):
        #print "<extra>orngDoc.py - resetActiveSignals() - ", outWidget, inWidget, newSignals
        signals = []
        for line in self.lines:
            if line.outWidget == outWidget and line.inWidget == inWidget:
                signals = line.getSignals()

        if newSignals == None:
            dialog = SignalDialog(self.canvasDlg, None, "", True)
            dialog.setOutInWidgets(outWidget, inWidget)
            for (outName, inName) in signals:
                #print "<extra>orngDoc.py - SignalDialog.addLink() - adding signal to dialog: ", outName, inName
                dialog.addLink(outName, inName)

            # if there are multiple choices, how to connect this two widget, then show the dialog
            res = dialog.exec_loop()
            if dialog.result() == QDialog.Rejected: return

            newSignals = dialog.getLinks()

        for (outName, inName) in signals:
            if (outName, inName) not in newSignals:
                self.removeLink(outWidget, inWidget, outName, inName)
                signals.remove((outName, inName))

        self.signalManager.setFreeze(1)
        for (outName, inName) in newSignals:
            if (outName, inName) not in signals:
                self.addLink(outWidget, inWidget, outName, inName, enabled)
        self.signalManager.setFreeze(0, outWidget.instance)

        outWidget.updateTooltip()
        inWidget.updateTooltip()

        self.enableSave(True)


    # #####################################
    # add one link (signal) from outWidget to inWidget. if line doesn't exist yet, we create it
    def addLink(self, outWidget, inWidget, outSignalName, inSignalName, enabled = 1):
        #print "<extra>orngDoc - addLink() - ", outWidget, inWidget, outSignalName, inSignalName
        # in case there already exists link to inSignalName in inWidget that is single, we first delete it
        widgetInstance = inWidget.instance.removeExistingSingleLink(inSignalName)
        if widgetInstance:
            widget = self.findWidgetFromInstance(widgetInstance)
            existingSignals = self.signalManager.findSignals(widgetInstance, inWidget.instance)
            for (outN, inN) in existingSignals:
                if inN == inSignalName:
                    self.removeLink(widget, inWidget, outN, inN)
                    line = self.getLine(widget, inWidget)
                    if line:
                        line.updateTooltip()

        # if line does not exist yet, we must create it
        existingSignals = self.signalManager.findSignals(outWidget.instance, inWidget.instance)
        if not existingSignals:
            line = orngCanvasItems.CanvasLine(self.signalManager, self.canvasDlg, self.canvasView, outWidget, inWidget, self.canvas)
            self.lines.append(line)
            line.setEnabled(enabled)
            line.show()
            outWidget.addOutLine(line)
            outWidget.updateTooltip()
            inWidget.addInLine(line)
            inWidget.updateTooltip()
        else:
            line = self.getLine(outWidget, inWidget)

        ok = self.signalManager.addLink(outWidget.instance, inWidget.instance, outSignalName, inSignalName, enabled)
        if not ok:
            self.removeLink(outWidget, inWidget, outSignalName, inSignalName)
            QMessageBox.warning( None, "Orange Canvas", "Unable to add link. Please rebuild widget registry and restart Orange Canvas for changes to take effect.", QMessageBox.Ok + QMessageBox.Default )
            return 0
        line.updateTooltip()
        return 1

    # ####################################
    # remove only one signal from connected two widgets. If no signals are left, delete the line
    def removeLink(self, outWidget, inWidget, outSignalName, inSignalName):
        #print "<extra> orngDoc.py - removeLink() - ", outWidget, inWidget, outSignalName, inSignalName
        self.signalManager.removeLink(outWidget.instance, inWidget.instance, outSignalName, inSignalName)

        otherSignals = 0
        if self.signalManager.links.has_key(outWidget.instance):
            for (widget, signalFrom, signalTo, enabled) in self.signalManager.links[outWidget.instance]:
                if widget == inWidget.instance:
                    otherSignals = 1
        if not otherSignals:
            self.removeLine(outWidget, inWidget)

        self.enableSave(True)

    # ####################################
    # remove line line
    def removeLine1(self, line):
        for (outName, inName) in line.getSignals():
            self.signalManager.removeLink(line.outWidget.instance, line.inWidget.instance, outName, inName)   # update SignalManager

        self.lines.remove(line)
        line.inWidget.removeLine(line)
        line.outWidget.removeLine(line)
        line.inWidget.updateTooltip()
        line.outWidget.updateTooltip()
        line.hide()
        line.remove()
        self.enableSave(True)

    # ####################################
    # remove line, connecting two widgets
    def removeLine(self, outWidget, inWidget):
        #print "<extra> orngDoc.py - removeLine() - ", outWidget, inWidget
        line = self.getLine(outWidget, inWidget)
        if line: self.removeLine1(line)

    # ####################################
    # add new widget
    def addWidget(self, widget, x= -1, y=-1, caption = "", activateSettings = 1):
        qApp.setOverrideCursor(QWidget.waitCursor)
        try:
            newwidget = orngCanvasItems.CanvasWidget(self.signalManager, self.canvas, self.canvasView, widget, self.canvasDlg.defaultPic, self.canvasDlg)
            newwidget.instance.category = widget.getCategory()
            newwidget.instance.setEventHandler(self.canvasDlg.output.widgetEvents)
        except:
            type, val, traceback = sys.exc_info()
            sys.excepthook(type, val, traceback)  # we pretend that we handled the exception, so that it doesn't crash canvas
            qApp.restoreOverrideCursor()
            return None
        qApp.restoreOverrideCursor()

        if x==-1 or y==-1:
            x = self.canvasView.contentsX() + 10
            for w in self.widgets:
                x = max(w.x() + 110, x)
                x = x/10*10
            y = 150
        newwidget.setCoords(x,y)
        self.canvasView.ensureVisible(x+50,y)
        newwidget.setViewPos(self.canvasView.contentsX(), self.canvasView.contentsY())

        if caption == "": caption = newwidget.caption

        if self.getWidgetByCaption(caption):
            i = 2
            while self.getWidgetByCaption(caption + " (" + str(i) + ")"): i+=1
            caption = caption + " (" + str(i) + ")"
        newwidget.updateText(caption)
        if (int(qVersion()[0]) >= 3):
            newwidget.instance.setCaptionTitle(caption)
        else:
            newwidget.instance.setCaptionTitle("Qt " + caption)

        # show the widget and activate the settings
        qApp.setOverrideCursor(QWidget.waitCursor)
        try:
            self.signalManager.addWidget(newwidget.instance)
            newwidget.show()
            newwidget.updateTooltip()
            newwidget.setProcessing(1)
            if activateSettings:
                newwidget.instance.activateLoadedSettings()
                if self.canvasDlg.settings["saveWidgetsPosition"]:
                    newwidget.instance.restoreWidgetPosition()
            newwidget.setProcessing(0)
        except:
            type, val, traceback = sys.exc_info()
            sys.excepthook(type, val, traceback)  # we pretend that we handled the exception, so that it doesn't crash canvas
        qApp.restoreOverrideCursor()

        self.widgets.append(newwidget)
        self.enableSave(True)
        self.canvas.update()
        return newwidget

    # ####################################
    # remove widget
    def removeWidget(self, widget):
        if not widget:
            return
        while widget.inLines != []: self.removeLine1(widget.inLines[0])
        while widget.outLines != []:  self.removeLine1(widget.outLines[0])

        self.signalManager.removeWidget(widget.instance)
        self.widgets.remove(widget)
        widget.remove()
        self.enableSave(True)

    def clear(self):
        for widget in self.widgets[::-1]:   self.removeWidget(widget)   # remove widgets from last to first
        self.canvas.update()

    def enableAllLines(self):
        for line in self.lines:
            self.signalManager.setLinkEnabled(line.outWidget.instance, line.inWidget.instance, 1)
            line.setEnabled(1)
            #line.repaintLine(self.canvasView)
        self.canvas.update()
        self.enableSave(True)

    def disableAllLines(self):
        for line in self.lines:
            self.signalManager.setLinkEnabled(line.outWidget.instance, line.inWidget.instance, 0)
            line.setEnabled(0)
            #line.repaintLine(self.canvasView)
        self.canvas.update()
        self.enableSave(True)

    # return a new widget instance of a widget with filename "widgetName"
    def addWidgetByFileName(self, widgetName, x, y, caption, activateSettings = 1):
        for widget in self.canvasDlg.tabs.allWidgets:
            if widget.getFileName() == widgetName:
                return self.addWidget(widget, x, y, caption, activateSettings)
        return None

    # return the widget instance that has caption "widgetName"
    def getWidgetByCaption(self, widgetName):
        for widget in self.widgets:
            if (widget.caption == widgetName):
                return widget
        return None

    def getWidgetCaption(self, widgetInstance):
        for widget in self.widgets:
            if widget.instance == widgetInstance:
                return widget.caption
        print "Error. Invalid widget instance : ", widgetInstance
        return ""

    # ####################################
    # get line from outWidget to inWidget
    def getLine(self, outWidget, inWidget):
        for line in self.lines:
            if line.outWidget == outWidget and line.inWidget == inWidget:
                return line
        return None

    # ####################################
    # find orngCanvasItems.CanvasWidget from widget instance
    def findWidgetFromInstance(self, widgetInstance):
        for widget in self.widgets:
            if widget.instance == widgetInstance:
                return widget
        return None

    # ###########################################
    # SAVING, LOADING, ....
    # ###########################################
    def saveDocument(self):
        if not self.documentnameValid:
            self.saveDocumentAs()
        else:
            self.save()

    def saveDocumentAs(self):
        qname = QFileDialog.getSaveFileName( os.path.join(self.documentpath, self.documentname), "Orange Widget Scripts (*.ows)", self, "", "Save File")
        name = str(qname)
        if os.path.splitext(name)[0] == "": return
        if os.path.splitext(name)[1] == "": name = name + ".ows"

        (self.documentpath, self.documentname) = os.path.split(name)
        self.canvasDlg.settings["saveSchemaDir"] = self.documentpath
        self.applicationname = os.path.splitext(os.path.split(name)[1])[0] + ".py"
        self.setCaption(self.documentname)
        self.documentnameValid = True
        self.save()

    # ####################################
    # save the file
    def save(self, filename = None):
        self.enableSave(False)

        # create xml document
        doc = Document()
        schema = doc.createElement("schema")
        widgets = doc.createElement("widgets")
        lines = doc.createElement("channels")
        settings = doc.createElement("settings")
        doc.appendChild(schema)
        schema.appendChild(widgets)
        schema.appendChild(lines)
        schema.appendChild(settings)
        settingsDict = {}

        #save widgets
        for widget in self.widgets:
            temp = doc.createElement("widget")
            temp.setAttribute("xPos", str(int(widget.x())) )
            temp.setAttribute("yPos", str(int(widget.y())) )
            temp.setAttribute("caption", widget.caption)
            temp.setAttribute("widgetName", widget.widget.getFileName())
            settingsDict[widget.caption] = widget.instance.saveSettingsStr()
            widgets.appendChild(temp)

        #save connections
        for line in self.lines:
            temp = doc.createElement("channel")
            temp.setAttribute("outWidgetCaption", line.outWidget.caption)
            temp.setAttribute("inWidgetCaption", line.inWidget.caption)
            temp.setAttribute("enabled", str(line.getEnabled()))
            temp.setAttribute("signals", str(line.getSignals()))
            lines.appendChild(temp)

        settings.setAttribute("settingsDictionary", str(settingsDict))

        xmlText = doc.toprettyxml()

        if filename != None:
            file = open(filename, "wt")
        else:
            file = open(os.path.join(self.documentpath, self.documentname), "wt")

        file.write(xmlText)
        file.flush()
        file.close()
        doc.unlink()

        #self.saveWidgetSettings(os.path.join(self.documentpath, os.path.splitext(self.documentname)[0]) + ".sav")
        if not filename:
            self.canvasDlg.addToRecentMenu(os.path.join(self.documentpath, self.documentname))

    def saveWidgetSettings(self, filename):
        list = {}
        for widget in self.widgets:
            list[widget.caption] = widget.instance.saveSettingsStr()

        file = open(filename, "wt")
        cPickle.dump(list, file)
        file.close()


    # ####################################
    # load a scheme with name "filename"
    def loadDocument(self, filename, caption = None):
        if not os.path.exists(filename):
            self.close()
            QMessageBox.critical(self,'Orange Canvas','Unable to find file "%s"' % filename,  QMessageBox.Ok + QMessageBox.Default)
            return

        # set cursor
        qApp.setOverrideCursor(QWidget.waitCursor)

        try:
            # ##################
            #load the data ...
            doc = parse(str(filename))
            schema = doc.firstChild
            widgets = schema.getElementsByTagName("widgets")[0]
            lines = schema.getElementsByTagName("channels")[0]
            settings = schema.getElementsByTagName("settings")

            (self.documentpath, self.documentname) = os.path.split(filename)
            (self.applicationpath, self.applicationname) = os.path.split(filename)
            self.applicationname = os.path.splitext(self.applicationname)[0] + ".py"
            settingsDict = eval(str(settings[0].getAttribute("settingsDictionary")))
            self.loadedSettingsDict = settingsDict
            self.canvasDlg.settings["saveApplicationDir"] = self.applicationpath

            # read widgets
            for widget in widgets.getElementsByTagName("widget"):
                name = widget.getAttribute("widgetName")
                tempWidget = self.addWidgetByFileName(name, int(widget.getAttribute("xPos")), int(widget.getAttribute("yPos")), widget.getAttribute("caption"), activateSettings = 0)
                if not tempWidget:
                    QMessageBox.information(self,'Orange Canvas','Unable to create an instance of the widget "%s"' % name,  QMessageBox.Ok + QMessageBox.Default)
                else:
                    if tempWidget.caption in settingsDict.keys():
                        tempWidget.instance.loadSettingsStr(settingsDict[tempWidget.caption])
                        tempWidget.instance.activateLoadedSettings()
                #qApp.processEvents()

            #read lines
            lineList = lines.getElementsByTagName("channel")
            for line in lineList:
                inCaption = line.getAttribute("inWidgetCaption")
                outCaption = line.getAttribute("outWidgetCaption")
                Enabled = int(line.getAttribute("enabled"))
                signals = line.getAttribute("signals")
                inWidget = self.getWidgetByCaption(inCaption)
                outWidget = self.getWidgetByCaption(outCaption)
                if inWidget == None or outWidget == None:
                    print 'Unable to connect etween widgets "%s" and "%s" due to a missing widget.' % (outCaption, inCaption)
                    continue

                signalList = eval(signals)
                for (outName, inName) in signalList:
                    self.addLink(outWidget, inWidget, outName, inName, Enabled)
                qApp.processEvents()

            for widget in self.widgets: widget.updateTooltip()
            self.canvas.update()
            self.enableSave(False)

            if caption != None: self.setCaption(caption)
            else:               self.setCaption(self.documentname)
            self.documentnameValid = True
            if self.widgets:
                self.signalManager.processNewSignals(self.widgets[0].instance)

            # do we want to restore last position and size of the widget
            if self.canvasDlg.settings["saveWidgetsPosition"]:
                for widget in self.widgets:
                    widget.instance.restoreWidgetStatus()
        finally:
            # set cursor
            qApp.setOverrideCursor(QWidget.arrowCursor)


    # ###########################################
    # save document as application
    # ###########################################
    def saveDocumentAsApp(self, asTabs = 1):
        # get filename
        extension = sys.platform == "win32" and ".pyw" or ".py"
        appName = os.path.splitext(self.applicationname)[0] + extension
        qname = QFileDialog.getSaveFileName( os.path.join(self.applicationpath, appName) , "Orange Scripts (*%s)" % extension, self, "", "Save File as Application")
        if qname.isEmpty(): return

        saveDlg = saveApplicationDlg(None, "", True)

        # add widget captions
        for instance in self.signalManager.widgets:
            widget = None
            for i in range(len(self.widgets)):
                if self.widgets[i].instance == instance: saveDlg.insertWidgetName(self.widgets[i].caption)

        res = saveDlg.exec_loop()
        if saveDlg.result() == QDialog.Rejected:
            return

        shownWidgetList = saveDlg.shownWidgetList
        hiddenWidgetList = saveDlg.hiddenWidgetList

        (self.applicationpath, self.applicationname) = os.path.split(str(qname))
        fileName = os.path.splitext(self.applicationname)[0]
        if os.path.splitext(self.applicationname)[1][:3] != ".py": self.applicationname += extension

        #format string with file content
        t = "    "  # instead of tab
        n = "\n"
        imports = """import sys, os, cPickle, orange, orngSignalManager, orngRegistry
DEBUG_MODE = 0   #set to 1 to output debugging info to file 'signalManagerOutput.txt'
orngRegistry.addWidgetDirectories()\n"""

        captions = "# set widget captions\n" +t+t
        instancesT = "# create widget instances\n" +t+t
        instancesB = "# create widget instances\n" +t+t
        tabs = "# add tabs\n"+t+t
        links = "#load settings before we connect widgets\n" +t+t+ "self.loadSettings()\n\n" +t+t + "# add widget signals\n"+t+t + "self.signalManager.setFreeze(1)\n" +t+t
        buttons = "# create widget buttons\n"+t+t
        buttonsConnect = "#connect GUI buttons to show widgets\n"+t+t
        icons = "# set icons\n"+t+t
        manager = ""
        loadSett = ""
        saveSett = ""
        signals = "#set event and progress handler\n"+t+t
        synchronizeContexts = ""
        widgetInstanceList = "#list of widget instances\n" +t+t + "self.widgets = ["

        sepCount = 1
        # gui for shown widgets
        for widgetName in shownWidgetList:
            if widgetName != "[Separator]":
                widget = None
                for i in range(len(self.widgets)):
                    if self.widgets[i].caption == widgetName: widget = self.widgets[i]

                name = widget.caption
                name = name.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").replace("-", "").replace("+", "")
                imports += "from %s import *\n" % (widget.widget.getFileName())
                instancesT += "self.ow%s = %s (self.tabs, signalManager = self.signalManager)\n" % (name, widget.widget.getFileName())+t+t
                instancesB += "self.ow%s = %s(signalManager = self.signalManager)\n" %(name, widget.widget.getFileName()) +t+t
                signals += "self.ow%s.setEventHandler(self.eventHandler)\n" % (name) +t+t + "self.ow%s.setProgressBarHandler(self.progressHandler)\n" % (name) +t+t
                icons += "self.ow%s.setWidgetIcon('%s')\n" % (name, widget.widget.getIconName()) + t+t
                captions += "if (int(qVersion()[0]) >= 3):\n" +t+t+t + "self.ow%s.setCaptionTitle('%s')\n" %(name, widget.caption) +t+t + "else:\n" +t+t+t + "self.ow%s.setCaptionTitle('Qt %s')\n" %(name, widget.caption) +t+t
                manager += "self.signalManager.addWidget(self.ow%s)\n" %(name) +t+t
                tabs += """self.tabs.insertTab (self.ow%s, "%s")\n""" % (name , widget.caption) +t+t
                tabs += "self.ow%s.captionTitle = '%s'\n" % (name, widget.caption)+t+t
                tabs += "self.ow%s.setCaption(self.ow%s.captionTitle)\n" % (name, name) +t+t
                buttons += """owButton%s = QPushButton("%s", self)\n""" % (name, widget.caption) +t+t
                buttonsConnect += """self.connect(owButton%s ,SIGNAL("clicked()"), self.ow%s.reshow)\n""" % (name, name) +t+t
                loadSett += """self.ow%s.loadSettingsStr(strSettings["%s"])\n""" % (name, widget.caption) +t+t
                loadSett += """self.ow%s.activateLoadedSettings()\n""" % (name) +t+t
                saveSett += """strSettings["%s"] = self.ow%s.saveSettingsStr()\n""" % (widget.caption, name) +t+t
                synchronizeContexts = "self.ow%s.synchronizeContexts()\n" % (name) +t+t + synchronizeContexts
                widgetInstanceList += "self.ow%s, " % (name)
            else:
                buttons += "frameSpace%s = QFrame(self);  frameSpace%s.setMinimumHeight(10); frameSpace%s.setMaximumHeight(10)\n" % (str(sepCount), str(sepCount), str(sepCount)) +t+t
                sepCount += 1

        instancesT += n+t+t + "# create instances of hidden widgets\n\n" +t+t
        instancesB += n+t+t + "# create instances of hidden widgets\n\n" +t+t

        # gui for hidden widgets
        for widgetName in hiddenWidgetList:
            widget = None
            for i in range(len(self.widgets)):
                if self.widgets[i].caption == widgetName: widget = self.widgets[i]

            name = widget.caption
            name = name.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").replace("-", "").replace("+", "")
            imports += "from %s import *\n" % (widget.widget.getFileName())
            instancesT += "self.ow%s = %s (self.tabs, signalManager = self.signalManager)\n" % (name, widget.widget.getFileName())+t+t
            instancesB += "self.ow%s = %s(signalManager = self.signalManager)\n" %(name, widget.widget.getFileName()) +t+t
            signals += "self.ow%s.signalManager = self.signalManager\n" % (name) +t+t + "self.ow%s.setEventHandler(self.eventHandler)\n" % (name) +t+t + "self.ow%s.setProgressBarHandler(self.progressHandler)\n" % (name) +t+t
            manager += "self.signalManager.addWidget(self.ow%s)\n" %(name) +t+t
            tabs += """self.tabs.insertTab (self.ow%s, "%s")\n""" % (name , widget.caption) +t+t
            loadSett += """self.ow%s.loadSettingsStr(strSettings["%s"])\n""" % (name, widget.caption) +t+t
            loadSett += """self.ow%s.activateLoadedSettings()\n""" % (name) +t+t
            saveSett += """strSettings["%s"] = self.ow%s.saveSettingsStr()\n""" % (widget.caption, name) +t+t
            widgetInstanceList += "self.ow%s, " % (name)

        for line in self.lines:
            if not line.getEnabled(): continue

            outWidgetName = line.outWidget.caption
            outWidgetName = outWidgetName.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").replace("-", "").replace("+", "")
            inWidgetName = line.inWidget.caption
            inWidgetName = inWidgetName.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").replace("-", "").replace("+", "")

            for (outName, inName) in line.getSignals():
                links += "self.signalManager.addLink( self.ow" + outWidgetName + ", self.ow" + inWidgetName + ", '" + outName + "', '" + inName + "', 1)\n" +t+t

        widgetInstanceList += "]"
        links += "self.signalManager.setFreeze(0)\n" +t+t
        buttons += "frameSpace = QFrame(self);  frameSpace.setMinimumHeight(20); frameSpace.setMaximumHeight(20)\n"+t+t
        buttons += "exitButton = QPushButton(\"E&xit\",self)\n"+t+t + "self.connect(exitButton,SIGNAL(\"clicked()\"), application, SLOT(\"quit()\"))\n"+t+t

        classinit = """
    def __init__(self,parent=None, debugMode = DEBUG_MODE, debugFileName = "signalManagerOutput.txt", verbosity = 1):
        QVBox.__init__(self,parent)
        caption = '%s'
        if (int(qVersion()[0]) >= 3):
            self.setCaption(caption)
        else:
            self.setCaption("Qt " + caption)
        self.signalManager = orngSignalManager.SignalManager(debugMode, debugFileName, verbosity)
        self.verbosity = verbosity""" % (fileName)

        if asTabs == 1:
            classinit += """
        self.tabs = QTabWidget(self, 'tabWidget')
        self.resize(800,600)"""

        progress = """
        statusBar = QStatusBar(self)
        self.progress = QProgressBar(100, statusBar)
        self.progress.setMaximumWidth(100)
        self.progress.setCenterIndicator(1)
        self.status = QLabel("", statusBar)
        self.status.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred))
        statusBar.addWidget(self.progress, 1)
        statusBar.addWidget(self.status, 1)"""

        handlerFunct = """
    def eventHandler(self, text, eventVerbosity = 1):
        if self.verbosity >= eventVerbosity:
            self.status.setText(text)

    def progressHandler(self, widget, val):
        if val < 0:
            self.status.setText("<nobr>Processing: <b>" + str(widget.captionTitle) + "</b></nobr>")
            self.progress.setProgress(0)
        elif val >100:
            self.status.setText("")
            self.progress.reset()
        else:
            self.progress.setProgress(val)
            self.update()"""

        loadSettings = """

    def loadSettings(self):
        try:
            file = open("%s", "r")
        except:
            return
        strSettings = cPickle.load(file)
        file.close()
        """ % (fileName + ".sav")
        loadSettings += loadSett

        saveSettings = """

    def saveSettings(self):
        if DEBUG_MODE: return
        %s
        strSettings = {}
        """ % (synchronizeContexts) + saveSett + n+t+t + """file = open("%s", "w")
        cPickle.dump(strSettings, file)
        file.close()
        """ % (fileName + ".sav")


        finish = """
if __name__ == "__main__":
    application = QApplication(sys.argv)
    ow = GUIApplication()
    application.setMainWidget(ow)
    ow.show()

    # comment the next line if in debugging mode and are interested only in output text in 'signalManagerOutput.txt' file
    application.exec_loop()
    ow.saveSettings()
"""

        #if save != "":
        #    save = t+"def exit(self):\n" +t+t+ save

        if asTabs:
            whole = imports + "\n\n" + "class GUIApplication(QVBox):" + classinit + n+n+t+t+ instancesT + signals + n+t+t + widgetInstanceList+n+t+t + progress + n+t+t + manager + n+t+t + tabs + n+ t+t + links + n+ handlerFunct + "\n\n" + loadSettings + saveSettings + "\n\n" + finish
        else:
            whole = imports + "\n\n" + "class GUIApplication(QVBox):" + classinit + "\n\n"+t+t+ instancesB + signals + n+n+t+t+ widgetInstanceList +n+t+t + captions + n+t+t+ icons + n+t+t + manager + n+t+t + buttons + n + progress + n +t+t+  buttonsConnect + n +t+t + links + "\n\n" + handlerFunct + "\n\n" + loadSettings + saveSettings + "\n\n" + finish

        #save app
        fileApp = open(os.path.join(self.applicationpath, self.applicationname), "wt")
        self.canvasDlg.settings["saveApplicationDir"] = self.applicationpath
        fileApp.write(whole)
        fileApp.flush()
        fileApp.close()

        # save settings
        self.saveWidgetSettings(os.path.join(self.applicationpath, fileName) + ".sav")

    def dumpWidgetVariables(self):
        for widget in self.widgets:
            self.canvasDlg.output.write("<hr><br><b>%s</b><br>" % (widget.caption))
            v = vars(widget.instance).keys()
            v.sort()
            for val in v:
                self.canvasDlg.output.write("%s = %s" % (val, getattr(widget.instance, val)))

    def keyReleaseEvent(self, e):
        self.ctrlPressed = e.state() & e.ControlButton

    def keyPressEvent(self, e):
        self.ctrlPressed = e.state() & e.ControlButton
        if e.key() > 127:
            QMainWindow.keyPressEvent(self, e)
            return

        # the list could include (e.ShiftButton, "Shift") if the shift key didn't have the special meaning
        pressed = "-".join(filter(None, [e.state() & x and y for x, y in [(e.ControlButton, "Ctrl"), (e.AltButton, "Alt")]]) + [chr(e.key())])
        widgetToAdd = self.canvasDlg.widgetShortcuts.get(pressed)
        if widgetToAdd:
            widgetToAdd.clicked()
            if e.state() & e.ShiftButton and len(self.widgets) > 1:
                self.addLine(self.widgets[-2], self.widgets[-1])
        else:
            QMainWindow.keyPressEvent(self, e)


if __name__=='__main__':
    app = QApplication(sys.argv)
    dlg = SchemaDoc()
    app.setMainWidget(dlg)
    dlg.show()
    app.exec_loop()