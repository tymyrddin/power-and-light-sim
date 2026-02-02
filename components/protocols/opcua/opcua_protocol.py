"""
OPC UA protocol abstraction.

Library-agnostic attacker behaviour for OPC UA.
Concrete OPC UA client implementations are injected.
"""

from components.protocols.base_protocol import BaseProtocol


class OPCUAProtocol(BaseProtocol):
    """
    OPC UA protocol wrapper exposing attacker-meaningful actions.

    Expected adapter interface (duck-typed, async):
      - connect() -> bool
      - disconnect() -> None
      - browse_root() -> list
      - read_node(node_id) -> object
      - write_node(node_id, value) -> bool
    """

    def __init__(self, adapter):
        super().__init__("opcua")
        self.adapter = adapter

    # ------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------

    async def connect(self) -> bool:
        self.connected = await self.adapter.connect()
        return self.connected

    async def disconnect(self) -> None:
        if self.connected:
            await self.adapter.disconnect()
        self.connected = False

    # ------------------------------------------------------------
    # recon
    # ------------------------------------------------------------

    async def probe(self) -> dict[str, object]:
        result: dict[str, object] = {
            "protocol": self.protocol_name,
            "connected": False,
            "browse": False,
            "read": False,
            "write": False,
        }

        if not await self.connect():
            return result

        result["connected"] = True

        nodes = None
        node_id = None
        value = None

        # ---- browse ----
        try:
            nodes = await self.adapter.browse_root()
            if nodes:
                result["browse"] = True
        except Exception:
            pass

        # ---- read ----
        try:
            if result["browse"] and nodes:
                node_id = nodes[0]
                value = await self.adapter.read_node(node_id)
                result["read"] = value is not None
        except Exception:
            pass

        # ---- write ----
        try:
            if result["browse"] and node_id is not None and value is not None:
                write_success = await self.adapter.write_node(node_id, value)
                result["write"] = write_success
        except Exception:
            pass

        await self.disconnect()
        return result

    # ------------------------------------------------------------
    # exploitation primitives
    # ------------------------------------------------------------

    async def browse(self):
        return await self.adapter.browse_root()

    async def read(self, node_id):
        return await self.adapter.read_node(node_id)

    async def write(self, node_id, value):
        return await self.adapter.write_node(node_id, value)
