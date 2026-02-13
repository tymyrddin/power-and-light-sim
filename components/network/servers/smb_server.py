# components/network/servers/smb_server.py
"""
SMB Server - Legacy Workstation Attack Surface.

Opens a REAL SMB port that external tools can connect to.
Serves the device's simulated filesystem via impacket's SimpleSMBServer.
Provides an interactive console via named pipe (\\pipe\\console) backed
by the device's DeviceFilesystem — Win98 command prompt experience.

Based on impacket 0.13.0 SimpleSMBServer.
"""

import asyncio
import configparser
import os
import shutil
import socket
import tempfile
import threading
from typing import Any

from pymodbus.client import ModbusTcpClient

from components.network.connection_registry import ConnectionRegistry
from components.network.servers.base_server import BaseProtocolServer
from components.security.logging_system import EventSeverity


# ====================================================================
# Console Server — Win98 command prompt over named pipe
# ====================================================================


class ConsoleServer(threading.Thread):
    """TCP server backing the \\pipe\\console named pipe.

    Provides a Windows 98 command prompt experience backed by a
    DeviceFilesystem. When a client opens the pipe, they get an
    interactive DOS session — dir, cd, type, etc.

    Registered with impacket's SMBSERVER via registerNamedPipe().
    Each client connection gets its own handler thread.
    """

    def __init__(self, filesystem: Any, device_name: str = "unknown"):
        super().__init__(daemon=True, name=f"console-{device_name}")
        self.filesystem = filesystem
        self.device_name = device_name
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._port = self._sock.getsockname()[1]

    def get_port(self) -> int:
        return self._port

    def run(self) -> None:
        self._sock.listen(5)
        while True:
            try:
                client, _ = self._sock.accept()
            except OSError:
                break
            threading.Thread(
                target=self._handle_session,
                args=(client,),
                daemon=True,
            ).start()

    def stop(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    def _handle_session(self, sock: socket.socket) -> None:
        """Handle one console session — Win98 command prompt."""
        cwd = "C:"
        modbus: dict | None = None

        welcome = (
            "\r\nMicrosoft(R) Windows 98\r\n"
            "   (C) Copyright Microsoft Corp 1981-1998.\r\n"
            f"\r\n{cwd}\\>"
        )
        try:
            sock.sendall(welcome.encode("utf-8"))
        except OSError:
            sock.close()
            return

        buf = b""
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data

                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    cmd = line.decode("utf-8", errors="replace").strip().rstrip("\r")

                    if modbus:
                        output, modbus = self._turbinelink_command(cmd, modbus)
                    else:
                        if cmd.lower() in ("exit", "quit"):
                            sock.shutdown(socket.SHUT_RDWR)
                            return
                        output, cwd, modbus = self._process_command(cmd, cwd)

                    prompt = "TurbineLink>" if modbus else f"{cwd}\\>"
                    response = f"\r\n{output}\r\n{prompt}" if output else f"\r\n{prompt}"
                    sock.sendall(response.encode("utf-8"))
        except (OSError, BrokenPipeError):
            pass
        finally:
            if modbus and modbus.get("client"):
                try:
                    modbus["client"].close()
                except Exception:
                    pass
            try:
                sock.close()
            except OSError:
                pass

    def _process_command(self, cmd: str, cwd: str) -> tuple[str, str, dict | None]:
        """Process a DOS command. Returns (output, new_cwd, modbus_state)."""
        if not cmd:
            return "", cwd, None

        parts = cmd.split(None, 1)
        verb = parts[0].lower()
        if verb.endswith(".exe"):
            verb = verb[:-4]
        arg = parts[1].strip() if len(parts) > 1 else ""

        if verb == "dir":
            return self._cmd_dir(cwd, arg), cwd, None
        elif verb == "cd":
            output, new_cwd = self._cmd_cd(cwd, arg)
            return output, new_cwd, None
        elif verb == "type":
            return self._cmd_type(cwd, arg), cwd, None
        elif verb in ("turblink", "turbinelink"):
            output, modbus = self._cmd_turblink()
            return output, cwd, modbus
        elif verb == "help":
            return self._cmd_help(), cwd, None
        elif verb == "ver":
            return "Windows 98 [Version 4.10.1998]", cwd, None
        elif verb == "cls":
            return "", cwd, None
        else:
            return f"Bad command or file name\n'{cmd}'", cwd, None

    def _to_fs_path(self, cwd: str, arg: str = "") -> str:
        """Convert cwd + optional arg to a DeviceFilesystem path."""
        if arg:
            # Absolute path (e.g. C:\TURBINE)
            if len(arg) > 1 and arg[1] == ":":
                return arg.replace("\\", "/")
            # Relative path
            base = cwd.replace("\\", "/")
            return base.rstrip("/") + "/" + arg.replace("\\", "/")
        return cwd.replace("\\", "/")

    def _cmd_dir(self, cwd: str, arg: str) -> str:
        """DIR — Win98 style directory listing."""
        path = self._to_fs_path(cwd, arg)
        entries = self.filesystem.list_dir(path)

        if not entries and not self.filesystem.is_directory(path):
            return "File not found"

        drive = path[0] if path and path[0].isalpha() else "C"
        display_path = path.replace("/", "\\")
        lines = [
            f" Volume in drive {drive} has no label",
            f" Directory of {display_path}",
            "",
            f"{'.':<14} <DIR>",
            f"{'..':<14} <DIR>",
        ]

        total_size = 0
        file_count = 0

        for entry in entries:
            name = entry["name"]
            if entry["type"] == "directory":
                lines.append(f"{name:<14} <DIR>        {entry['modified']}")
            else:
                size = entry.get("size", 0)
                total_size += size
                file_count += 1
                lines.append(f"{name:<14} {size:>10,}  {entry['modified']}")

        lines.append(f"        {file_count} file(s)    {total_size:>10,} bytes")
        return "\n".join(lines)

    def _cmd_cd(self, cwd: str, arg: str) -> tuple[str, str]:
        """CD — change directory."""
        if not arg:
            return cwd.replace("/", "\\"), cwd

        if arg == "\\" or arg == "/":
            drive = cwd.replace("\\", "/").split("/")[0]
            return "", drive

        if arg == "..":
            parts = cwd.replace("\\", "/").rstrip("/").split("/")
            if len(parts) > 1:
                new_cwd = "/".join(parts[:-1])
            else:
                new_cwd = parts[0]
            return "", new_cwd

        new_path = self._to_fs_path(cwd, arg)
        if self.filesystem.is_directory(new_path):
            return "", new_path
        return f"Invalid directory - {arg}", cwd

    def _cmd_type(self, cwd: str, arg: str) -> str:
        """TYPE — display file contents."""
        if not arg:
            return "Required parameter missing"

        path = self._to_fs_path(cwd, arg)
        contents = self.filesystem.read_file(path)
        if contents is None:
            return f"File not found - {arg}"
        return contents

    def _cmd_help(self) -> str:
        """HELP — list available commands."""
        return (
            "CD       Change directory\n"
            "CLS      Clear screen\n"
            "DIR      Display directory listing\n"
            "EXIT     Close this session\n"
            "HELP     Display this help\n"
            "TURBLINK Launch TurbineLink PLC monitor\n"
            "TYPE     Display contents of a text file\n"
            "VER      Display Windows version"
        )

    # ================================================================
    # TurbineLink — PLC monitoring software (pivot to Modbus)
    # ================================================================

    @staticmethod
    def _parse_register_map(parser: configparser.ConfigParser) -> dict:
        """Parse [Registers] section into ir/hr/coil/di maps."""
        ir, hr, coils, di = {}, {}, {}, {}
        if not parser.has_section("Registers"):
            return {"ir": ir, "hr": hr, "coils": coils, "di": di}

        for key, val in parser.items("Registers"):
            if key.startswith("ir"):
                addr = int(key[2:])
                parts = val.split(",")
                name = parts[0]
                unit = parts[1] if len(parts) > 1 else ""
                scale = int(parts[2]) if len(parts) > 2 else 1
                ir[addr] = (name, unit, scale)
            elif key.startswith("hr"):
                addr = int(key[2:])
                parts = val.split(",")
                name = parts[0]
                unit = parts[1] if len(parts) > 1 else ""
                hr[addr] = (name, unit)
            elif key.startswith("coil"):
                addr = int(key[4:])
                coils[addr] = val
            elif key.startswith("di"):
                addr = int(key[2:])
                di[addr] = val

        return {"ir": ir, "hr": hr, "coils": coils, "di": di}

    def _cmd_turblink(self) -> tuple[str, dict | None]:
        """Launch TurbineLink — reads config.ini, connects to PLC device."""
        config_contents = self.filesystem.read_file("C:/TURBINE/config.ini")
        if config_contents is None:
            return "Error: config.ini not found", None

        parser = configparser.ConfigParser()
        try:
            parser.read_string(config_contents)
        except configparser.Error:
            return "Error: Cannot parse config.ini", None

        plc_address = parser.get("Network", "PLCAddress", fallback=None)
        plc_port = parser.get("Network", "PLCPort", fallback=None)

        if not plc_address or not plc_port:
            return "Error: PLCAddress/PLCPort not configured", None

        try:
            port = int(plc_port)
        except ValueError:
            return f"Error: Invalid port '{plc_port}'", None

        target = f"{plc_address}:{plc_port}"
        banner = (
            "TurboDynamics TurbineLink Pro 2.1\n"
            "(C) 1997 TurboDynamics Inc.\n"
            f"\nConnecting to PLC at {target}..."
        )

        try:
            client = ModbusTcpClient("127.0.0.1", port=port, timeout=5)
            if not client.connect():
                return f"{banner}\nError: Connection refused", None
        except Exception as e:
            return f"{banner}\nError: {e}", None

        reg_map = self._parse_register_map(parser)
        modbus = {
            "client": client,
            "target": target,
            "reg_map": reg_map,
        }
        status = self._turbinelink_status(modbus)
        return f"{banner}\nConnected.\n\n{status}\n\nType 'help' for commands.", modbus

    def _turbinelink_command(self, cmd: str, modbus: dict) -> tuple[str, dict | None]:
        """Process a TurbineLink command."""
        if not cmd:
            return "", modbus

        parts = cmd.split()
        verb = parts[0].lower()

        if verb in ("exit", "quit", "disconnect"):
            try:
                modbus["client"].close()
            except Exception:
                pass
            return "Disconnected from PLC.", None
        elif verb == "status":
            return self._turbinelink_status(modbus), modbus
        elif verb == "read":
            return self._turbinelink_read(parts[1:], modbus), modbus
        elif verb == "write":
            return self._turbinelink_write(parts[1:], modbus), modbus
        elif verb == "help":
            return self._turbinelink_help(modbus), modbus
        else:
            return f"Unknown command: {verb}", modbus

    def _turbinelink_status(self, modbus: dict) -> str:
        """Read and display turbine status via Modbus."""
        client = modbus["client"]
        reg_map = modbus.get("reg_map", {"ir": {}, "hr": {}, "coils": {}, "di": {}})
        lines = [f"=== Turbine Status ({modbus['target']}) ===", ""]

        if reg_map["ir"]:
            max_addr = max(reg_map["ir"]) + 1
            try:
                result = client.read_input_registers(0, count=max_addr)
                if not result.isError():
                    for addr in sorted(reg_map["ir"]):
                        name, unit, scale = reg_map["ir"][addr]
                        val = result.registers[addr]
                        if scale > 1:
                            lines.append(f"  {name:<20} {val/scale:.1f} {unit}")
                        elif unit == "%":
                            lines.append(f"  {name:<20} {val}%")
                        else:
                            lines.append(f"  {name:<20} {val} {unit}")
            except Exception as e:
                lines.append(f"  Error reading telemetry: {e}")

        lines.append("")

        for addr in sorted(reg_map["hr"]):
            name, unit = reg_map["hr"][addr]
            try:
                result = client.read_holding_registers(addr, count=1)
                if not result.isError():
                    lines.append(f"  {name:<20} {result.registers[0]} {unit}")
            except Exception:
                pass

        lines.append("")

        if reg_map["coils"]:
            max_coil = max(reg_map["coils"]) + 1
            try:
                result = client.read_coils(0, count=max_coil)
                if not result.isError():
                    for addr in sorted(reg_map["coils"]):
                        name = reg_map["coils"][addr]
                        if addr < len(result.bits):
                            lines.append(f"  {name:<20} {'ON' if result.bits[addr] else 'OFF'}")
            except Exception:
                pass

        if reg_map["di"]:
            max_di = max(reg_map["di"]) + 1
            try:
                result = client.read_discrete_inputs(0, count=max_di)
                if not result.isError():
                    for addr in sorted(reg_map["di"]):
                        name = reg_map["di"][addr]
                        if addr < len(result.bits):
                            lines.append(f"  {name:<20} {'ON' if result.bits[addr] else 'OFF'}")
            except Exception:
                pass

        return "\n".join(lines)

    def _turbinelink_read(self, args: list[str], modbus: dict) -> str:
        """Read registers. Usage: read hr|ir|coil|di <addr> [count]"""
        if len(args) < 2:
            return "Usage: read hr|ir|coil|di <addr> [count]"

        reg_type = args[0].lower()
        try:
            addr = int(args[1])
            count = int(args[2]) if len(args) > 2 else 1
        except ValueError:
            return "Error: address and count must be numbers"

        client = modbus["client"]
        try:
            if reg_type == "hr":
                result = client.read_holding_registers(addr, count=count)
            elif reg_type == "ir":
                result = client.read_input_registers(addr, count=count)
            elif reg_type == "coil":
                result = client.read_coils(addr, count=count)
            elif reg_type == "di":
                result = client.read_discrete_inputs(addr, count=count)
            else:
                return "Error: type must be hr, ir, coil, or di"

            if result.isError():
                return f"Error: {result}"

            if reg_type in ("coil", "di"):
                lines = [
                    f"  {reg_type} {addr+i}: {'ON' if result.bits[i] else 'OFF'}"
                    for i in range(count)
                ]
            else:
                lines = [
                    f"  {reg_type} {addr+i}: {v}"
                    for i, v in enumerate(result.registers)
                ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def _turbinelink_write(self, args: list[str], modbus: dict) -> str:
        """Write register. Usage: write hr|coil <addr> <value>"""
        if len(args) < 3:
            return "Usage: write hr|coil <addr> <value>"

        reg_type = args[0].lower()
        try:
            addr = int(args[1])
            value = int(args[2])
        except ValueError:
            return "Error: address and value must be numbers"

        client = modbus["client"]
        try:
            if reg_type == "hr":
                result = client.write_register(addr, value)
            elif reg_type == "coil":
                result = client.write_coil(addr, value != 0)
            else:
                return "Error: type must be hr or coil"

            if result.isError():
                return f"Error: {result}"
            return f"OK: {reg_type} {addr} = {value}"
        except Exception as e:
            return f"Error: {e}"

    def _turbinelink_help(self, modbus: dict) -> str:
        """Help with full register map from config."""
        reg_map = modbus.get("reg_map", {"ir": {}, "hr": {}, "coils": {}, "di": {}})
        lines = [
            f"TurbineLink Pro 2.1 — {modbus['target']}",
            "",
            "Commands: status, read, write, help, exit",
            "",
        ]

        if reg_map["ir"]:
            lines.append("Telemetry (read-only):")
            for addr in sorted(reg_map["ir"]):
                name, unit, scale = reg_map["ir"][addr]
                suffix = f" (x{scale})" if scale > 1 else ""
                lines.append(f"  ir {addr:<4} {name:<20} {unit}{suffix}")
            lines.append("")

        if reg_map["hr"]:
            lines.append("Setpoints (read/write):")
            for addr in sorted(reg_map["hr"]):
                name, unit = reg_map["hr"][addr]
                lines.append(f"  hr {addr:<4} {name:<20} {unit}")
            lines.append("")

        if reg_map["coils"]:
            lines.append("Controls (read/write):")
            for addr in sorted(reg_map["coils"]):
                name = reg_map["coils"][addr]
                lines.append(f"  coil {addr:<3} {name}")
            lines.append("")

        if reg_map["di"]:
            lines.append("Status Flags (read-only):")
            for addr in sorted(reg_map["di"]):
                name = reg_map["di"][addr]
                lines.append(f"  di {addr:<4} {name}")
            lines.append("")

        lines.append("Examples:")
        lines.append("  status                 Show all values")
        lines.append("  read ir 0              Read speed")
        lines.append("  read ir 0 8            Read all input registers")
        lines.append("  write hr 0 3600        Set speed setpoint")
        lines.append("  write coil 1 1         Trigger emergency trip")
        lines.append("  exit                   Return to command prompt")
        return "\n".join(lines)


class SMBServer(BaseProtocolServer):
    """
    SMB server backed by a DeviceFilesystem.

    Materialises the simulated filesystem to a temp directory on disk,
    then serves it via impacket. External tools see real SMB shares
    with real files.

    Shares are defined by the device (e.g. TURBINE_DATA, BACKUP, C$).
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 445,
        server_name: str = "TURBINE-DATA",
        server_os: str = "Windows 4.0",
        device_name: str = "unknown",
        allow_anonymous: bool = True,
    ):
        super().__init__(host, port, device_name)
        self.server_name = server_name
        self.server_os = server_os
        self.allow_anonymous = allow_anonymous

        self._smb_server = None
        self._server_thread: threading.Thread | None = None
        self._temp_dir: str | None = None
        self._shares: dict[str, str] = {}
        self._running = False
        self._registry = ConnectionRegistry()
        self._active_sessions: dict[int, str] = {}  # connId -> session_id
        self._loop: asyncio.AbstractEventLoop | None = None
        self._console_server: ConsoleServer | None = None

    @property
    def running(self) -> bool:
        return self._running

    def set_filesystem(
        self,
        filesystem: Any,
        shares: dict[str, str],
    ) -> None:
        """
        Configure the filesystem to serve.

        Args:
            filesystem: DeviceFilesystem instance
            shares: Dict mapping share name to filesystem path prefix.
                    e.g. {"TURBINE_DATA": "C:/TURBINE/DATA", "C$": "C:/"}
        """
        self._filesystem = filesystem
        self._shares = shares

    def _materialise_filesystem(self) -> str:
        """Write the simulated filesystem to a real temp directory."""
        temp_dir = tempfile.mkdtemp(prefix=f"smb_{self.device_name}_")

        for key, entry in self._filesystem._files.items():
            if entry.file_type != "file":
                continue

            display_path = entry.metadata.get("_display_path", key)

            # Strip drive letter (C:/) and convert to local path
            relative = display_path
            if len(relative) > 2 and relative[1] == ":":
                relative = relative[2:]
            relative = relative.lstrip("/")

            real_path = os.path.join(temp_dir, relative)
            os.makedirs(os.path.dirname(real_path), exist_ok=True)

            with open(real_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(entry.contents)

        return temp_dir

    async def start(self) -> None:
        """Start the SMB server in a background thread."""
        if self._running:
            self.logger.warning(f"SMB server already running on port {self.port}")
            return

        if not hasattr(self, "_filesystem"):
            self.logger.error("No filesystem configured. Call set_filesystem() first.")
            return

        # Capture event loop for thread-safe scheduling from _auth_callback
        self._loop = asyncio.get_running_loop()

        self._temp_dir = self._materialise_filesystem()

        try:
            from impacket.smbserver import SimpleSMBServer

            self._smb_server = SimpleSMBServer(
                listenAddress=self.host,
                listenPort=self.port,
            )

            self._smb_server.setSMB2Support(False)  # Win98 = SMBv1 only

            if self.allow_anonymous:
                self._smb_server.setAuthCallback(self._auth_callback)

            for share_name, fs_path_prefix in self._shares.items():
                relative = fs_path_prefix
                if len(relative) > 2 and relative[1] == ":":
                    relative = relative[2:]
                relative = relative.lstrip("/")

                share_path = os.path.join(self._temp_dir, relative)
                if not os.path.isdir(share_path):
                    os.makedirs(share_path, exist_ok=True)

                self._smb_server.addShare(
                    share_name,
                    share_path,
                    shareComment=f"Share on {self.server_name}",
                    readOnly="no",
                )

                self.logger.info(
                    f"SMB share '{share_name}' -> {fs_path_prefix} "
                    f"(real: {share_path})"
                )

            # Register console named pipe (Win98 command prompt)
            self._console_server = ConsoleServer(
                self._filesystem, self.device_name,
            )
            self._console_server.start()
            self._smb_server.registerNamedPipe(
                "console",
                ("127.0.0.1", self._console_server.get_port()),
            )
            self.logger.info(
                f"Console pipe registered on port {self._console_server.get_port()}"
            )

            self._server_thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name=f"smb-{self.device_name}",
            )
            self._running = True
            self._server_thread.start()

            self.logger.info(
                f"SMB server '{self.server_name}' started on {self.host}:{self.port} "
                f"(device={self.device_name}, shares={list(self._shares.keys())})"
            )

            await self.logger.log_audit(
                message=f"SMB server started: {self.server_name} on port {self.port}",
                action="server_start",
                result="SUCCESS",
                user="system",
            )

            await self.log_security(
                message=(
                    f"SMB server '{self.server_name}' listening on port {self.port} "
                    f"(shares: {list(self._shares.keys())})"
                ),
                severity=EventSeverity.INFO,
                data={
                    "port": self.port,
                    "shares": list(self._shares.keys()),
                    "allow_anonymous": self.allow_anonymous,
                },
            )

        except Exception as e:
            self.logger.error(f"Failed to start SMB server: {e}")
            self._cleanup_temp()
            raise

    def _run_server(self) -> None:
        """Run the SMB server (blocking, runs in thread)."""
        try:
            self._smb_server.start()
        except Exception as e:
            if self._running:
                self.logger.error(f"SMB server error: {e}")

    def _auth_callback(self, connId, challenge, response):
        """
        Authentication callback — allows everything (null session).

        Called from impacket's thread. Uses run_coroutine_threadsafe
        to schedule async registry/audit work on the main event loop.
        """
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self._register_connection(connId), self._loop
            )
        return True

    async def _register_connection(self, connId: Any) -> None:
        """Register an SMB connection and log the audit event."""
        source_ip = str(connId) if connId else "unknown"

        session_id = await self._registry.connect(
            source_ip=source_ip,
            source_device="external",
            target_device=self.device_name,
            protocol="smb",
            port=self.port,
            metadata={"authentication": "null_session", "smb_version": "SMBv1"},
        )
        self._active_sessions[connId] = session_id

        await self.logger.log_audit(
            message=f"SMB null session from {source_ip}",
            action="connect",
            result="ALLOWED",
            user="anonymous",
        )

    async def refresh_filesystem(self) -> None:
        """
        Re-materialise dynamic files from the device filesystem.

        Call this to pick up changes (e.g. new log entries,
        forensic artefacts appended during the exercise).
        """
        if not self._temp_dir or not hasattr(self, "_filesystem"):
            return

        for key, entry in self._filesystem._files.items():
            if entry.file_type != "file":
                continue
            if not entry.metadata.get("dynamic", False):
                continue

            display_path = entry.metadata.get("_display_path", key)
            relative = display_path
            if len(relative) > 2 and relative[1] == ":":
                relative = relative[2:]
            relative = relative.lstrip("/")

            real_path = os.path.join(self._temp_dir, relative)
            os.makedirs(os.path.dirname(real_path), exist_ok=True)

            with open(real_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(entry.contents)

    async def stop(self) -> None:
        """Stop the SMB server and clean up."""
        self._running = False

        for conn_id, session_id in list(self._active_sessions.items()):
            await self._registry.kill_connection(
                session_id, reason="SMB server shutdown"
            )
        self._active_sessions.clear()

        if self._console_server:
            self._console_server.stop()
            self._console_server = None

        if self._smb_server:
            try:
                self._smb_server.stop()
            except Exception:
                pass
            self._smb_server = None

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5.0)
            self._server_thread = None

        self._cleanup_temp()
        self._loop = None
        self.logger.info(f"SMB server '{self.server_name}' stopped")

    def _cleanup_temp(self) -> None:
        """Remove the temp directory."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
            except Exception as e:
                self.logger.warning(f"Failed to clean temp dir: {e}")
            self._temp_dir = None

    def get_status(self) -> dict[str, Any]:
        """Get SMB server status."""
        status = super().get_status()
        status.update({
            "server_name": self.server_name,
            "shares": list(self._shares.keys()),
            "allow_anonymous": self.allow_anonymous,
            "smb_version": "SMBv1",
            "os": self.server_os,
        })
        return status