"""讀取 config/default.toml、config/local.toml 與科目設定。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
# 會寫入的資料（下載的名詞庫、各書術語表、my_terms、local.toml、預設輸出）放這裡。
# 從原始碼執行時就是專案資料夾；安裝版的程式在 Program Files 不能寫，
# 由桌面 App 用環境變數指到使用者的資料夾（%APPDATA%\textbook-tw）。
DATA_ROOT = Path(os.environ.get("TEXTBOOK_TW_HOME") or PROJECT_ROOT)

DUAL_MODES = ("side_by_side", "alternating", "both", "none")
FONTS = ("auto", "serif", "sans-serif")


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    description: str
    glossaries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Settings:
    base_url: str
    model: str
    lang_in: str
    lang_out: str
    profile: Profile
    glossary: bool
    output_dir: Path
    mono: bool
    dual: str
    translated_first: bool
    font: str

    def with_overrides(self, **overrides) -> Settings:
        """回傳套用指令列選項後的設定；值為 None 的選項不覆蓋。"""
        changes = {k: v for k, v in overrides.items() if v is not None}
        if "profile" in changes and isinstance(changes["profile"], str):
            changes["profile"] = load_profile(changes["profile"])
        updated = replace(self, **changes)
        _validate(updated)
        return updated


def _validate(settings: Settings) -> None:
    if settings.dual not in DUAL_MODES:
        raise ValueError(f"dual 必須是 {', '.join(DUAL_MODES)} 其中之一")
    if settings.font not in FONTS:
        raise ValueError(f"font 必須是 {', '.join(FONTS)} 其中之一")


def _merge(base: dict, extra: dict) -> dict:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def list_profiles() -> list[str]:
    return sorted(p.stem for p in (CONFIG_DIR / "profiles").glob("*.toml"))


def load_profile(profile_id: str) -> Profile:
    path = CONFIG_DIR / "profiles" / f"{profile_id}.toml"
    if not path.exists():
        raise ValueError(f"找不到科目設定 {profile_id}，可用的有：{', '.join(list_profiles())}")
    data = _read_toml(path)
    return Profile(
        id=profile_id,
        name=data.get("name", profile_id),
        description=data.get("description", ""),
        glossaries=list(data.get("glossaries", [])),
    )


def load_settings() -> Settings:
    data = _read_toml(CONFIG_DIR / "default.toml")
    local = DATA_ROOT / "config" / "local.toml"
    if local.exists():
        data = _merge(data, _read_toml(local))

    model, translation, output = data["model"], data["translation"], data["output"]
    output_dir = Path(output["dir"])
    if not output_dir.is_absolute():
        output_dir = DATA_ROOT / output_dir

    settings = Settings(
        base_url=model["base_url"],
        model=model["name"],
        lang_in=translation["lang_in"],
        lang_out=translation["lang_out"],
        profile=load_profile(translation["profile"]),
        glossary=translation.get("glossary", True),
        output_dir=output_dir,
        mono=output["mono"],
        dual=output["dual"],
        translated_first=output["translated_first"],
        font=output.get("font", "auto"),
    )
    _validate(settings)
    return settings
