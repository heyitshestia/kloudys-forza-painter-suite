import QtQuick 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

RowLayout {
    id: root

    property bool supporterOnly: false
    property string classificationLabel: "Toolmade"
    property string categoryLabel: "Other"
    property string schemaLabel: "KFPS-compatible JSON"
    property real textPixelSize: Theme.px(9.8)

    readonly property bool handmade: classificationLabel.trim().toLowerCase() === "handmade"
    readonly property color classificationColor: handmade
                                                    ? Theme.classificationHandmade
                                                    : Theme.classificationToolmade

    spacing: 0

    Text {
        visible: root.supporterOnly
        text: "Supporters | "
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: root.textPixelSize
    }

    Text {
        text: root.classificationLabel
        color: root.classificationColor
        font.family: Theme.fontFamily
        font.pixelSize: root.textPixelSize
        font.weight: Font.DemiBold
    }

    Text {
        Layout.fillWidth: true
        text: " | " + root.categoryLabel + " | " + root.schemaLabel
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: root.textPixelSize
        elide: Text.ElideRight
    }
}
