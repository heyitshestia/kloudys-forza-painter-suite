import QtQuick 6.7
import Kfps.Theme 1.0

Image {
    readonly property int checkerTileSize: Math.max(16, Math.round(Theme.px(24)))

    source: assetRoot + "/artwork-checker.svg"
    sourceSize.width: checkerTileSize
    sourceSize.height: checkerTileSize
    fillMode: Image.Tile
    asynchronous: false
    cache: true
    smooth: false
    mipmap: false
}
