from .chatagent import ChatAgent

# Keep SmallAgent import optional so ChatAgent can be used/tested
# even if legacy SmallAgent dependencies are not installed yet.
try:
    from .smallagent import SmallAgent
except ModuleNotFoundError:
    SmallAgent = None