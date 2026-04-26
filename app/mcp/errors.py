class MCPError(Exception):
    pass


class MCPConnectionError(MCPError):
    pass


class MCPTimeoutError(MCPError):
    pass


class MCPProtocolError(MCPError):
    pass


class MCPToolNotFoundError(MCPError):
    pass
