def classFactory(iface):
    from .gismark import GisMarkPlugin
    return GisMarkPlugin(iface)
