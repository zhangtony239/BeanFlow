"""
SSH 公钥校验模块。

用于去中心化审计权限系统，获取当前用户 SSH 公钥并校验。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def get_ssh_public_key() -> Optional[str]:
    """获取当前用户的 SSH 公钥（默认读取 ~/.ssh/id_rsa.pub）。"""
    ssh_dir = Path.home() / ".ssh"
    for keyfile in ["id_rsa.pub", "id_ed25519.pub", "id_ecdsa.pub"]:
        key_path = ssh_dir / keyfile
        if key_path.exists():
            content = key_path.read_text(encoding="utf-8").strip()
            if content:
                return content
    return None


def get_all_ssh_keys() -> list[str]:
    """获取当前用户所有 SSH 公钥。"""
    keys = []
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return keys
    for keyfile in ssh_dir.glob("*.pub"):
        content = keyfile.read_text(encoding="utf-8").strip()
        if content:
            keys.append(content)
    return keys


def verify_ssh_key(authorized_keys: list[str], key: str) -> bool:
    """校验给定的 SSH 公钥是否在授权列表中。

    支持精确匹配和前 N 字符匹配。
    """
    key_stripped = key.strip()
    for authorized in authorized_keys:
        auth_stripped = authorized.strip()
        if key_stripped == auth_stripped:
            return True
        # 前 80 字符匹配（容忍注释部分差异）
        if len(key_stripped) > 80 and len(auth_stripped) > 80:
            if key_stripped[:80] == auth_stripped[:80]:
                return True
    return False