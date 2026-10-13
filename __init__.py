def classFactory(iface):
    from .gismark_plugin import GisMarkPlugin
    return GisMarkPlugin(iface)
