"""Host, Group, and Tag data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Tag:
    """A colored label for organizing hosts."""

    id: int | None = None
    sync_uuid: str | None = None
    name: str = ""
    color: str = "#6c757d"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Group:
    """A collection of hosts with optional inherited settings."""

    id: int | None = None
    sync_uuid: str | None = None
    vault_id: int = 1
    parent_id: int | None = None
    name: str = ""
    icon: str = "folder"
    color: str | None = None
    default_identity_id: int | None = None
    default_jump_host_id: int | None = None
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Host:
    """A defined connection target."""

    id: int | None = None
    sync_uuid: str | None = None
    vault_id: int = 1
    group_id: int | None = None
    label: str = ""
    address: str = ""
    protocol: str = "ssh"

    # SSH settings
    ssh_port: int = 22
    ssh_identity_id: int | None = None
    ssh_host_chain_id: int | None = None
    ssh_startup_snippet_id: int | None = None
    ssh_keep_alive: int = 60
    ssh_agent_forwarding: bool = False
    ssh_x11_forwarding: bool = False
    ssh_compression: bool = False

    # RDP settings
    rdp_port: int = 3389
    rdp_username: str | None = None
    rdp_domain: str | None = None
    rdp_resolution: str = "1920x1080"
    rdp_color_depth: int = 32
    rdp_audio: bool = False
    rdp_clipboard: bool = True
    rdp_drive_mapping: str | None = None

    # VNC settings
    vnc_port: int = 5900
    vnc_quality: str = "auto"
    vnc_view_only: bool = False
    vnc_clipboard: bool = True

    # Telnet settings
    telnet_port: int = 23
    telnet_raw_mode: bool = False

    # Serial settings
    serial_port_path: str | None = None
    serial_baud_rate: int = 115200
    serial_data_bits: int = 8
    serial_stop_bits: str = "1"
    serial_parity: str = "none"
    serial_flow_control: str = "none"

    # Terminal appearance override
    terminal_theme: str | None = None
    terminal_font: str | None = None
    terminal_font_size: int | None = None

    # Meta
    notes: str | None = None
    color_label: str | None = None
    last_connected: datetime | None = None
    connect_count: int = 0
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Transient (not stored in DB directly)
    tags: list[Tag] = field(default_factory=list)
