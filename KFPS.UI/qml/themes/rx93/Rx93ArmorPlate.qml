import QtQuick 6.7

Item {
    id: root
    property string part: "navy-key"
    property real rim: 83
    // Scale the nine-slice coordinate system, not the fasteners with the width.
    readonly property real unit: Math.max(0.01, height / 793)
    BorderImage {
        width: root.width / root.unit
        height: 793
        scale: root.unit
        transformOrigin: Item.TopLeft
        source: assetRoot + "/themes/rx93-psycho-frame/parts/" + root.part + ".png"
        border { left: 258; right: 258; top: root.rim; bottom: root.rim + 20 }
        horizontalTileMode: BorderImage.Stretch
        verticalTileMode: BorderImage.Stretch
        smooth: true
    }
}
