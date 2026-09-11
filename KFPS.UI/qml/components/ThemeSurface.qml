import QtQuick 6.7

Loader {
    id: root
    property string componentFile: ""
    property var surfaceOwner: null
    property string ownerProperty: ""
    property string surfaceRole: ""
    readonly property bool usable: status === Loader.Ready
    active: componentFile.length > 0
    source: active ? Qt.resolvedUrl(componentFile) : ""
    asynchronous: false
    onLoaded: {
        if (ownerProperty.length > 0)
            item[ownerProperty] = surfaceOwner
        if (surfaceRole.length > 0)
            item.controlKind = surfaceRole
    }
}
