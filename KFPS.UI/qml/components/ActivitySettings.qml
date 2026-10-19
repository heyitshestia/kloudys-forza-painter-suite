import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

ColumnLayout {
    id: root
    property var service
    spacing: Theme.px(8)

    Timer {
        interval: 3000
        repeat: true
        triggeredOnStart: true
        running: root.visible && !!root.service
        onTriggered: root.service.refresh()
    }
    KfpsCheckBox {
        objectName: "anonymousActivityToggle"
        Layout.fillWidth: true
        text: "Anonymous activity counts"
        enabled: !!root.service
        checked: root.service ? root.service.enabled : false
        toolTipText: "Optional installation counts shared by KFPS, the editor and Livery Studio."
        onToggled: root.service.setEnabled(checked)
    }
    Text {
        objectName: "anonymousActivityPrivacy"
        Layout.fillWidth: true
        text: root.service ? root.service.privacyText : ""
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(12)
        renderType: Text.NativeRendering
        color: Theme.text
    }
    Text {
        objectName: "anonymousActivityError"
        Layout.fillWidth: true
        visible: text.length > 0
        text: root.service ? root.service.status : ""
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(12)
        renderType: Text.NativeRendering
        color: Theme.danger
    }
}
