from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import List


@dataclass
class Social:
    Name: str
    Url: str
    Icon: str


@dataclass
class __DYN__:
    P_Version: str
    B_Version: str
    New: bool
    Debug: bool
    sha: str


@dataclass
class BRD_Datas:
    Package_name: str
    Socials: List[Social]
    Custom_Category: dict
    Repository: str
    Folder: Path
    __DYN__: __DYN__

    def File_Location(self) -> Path:
        return Path(
            PurePath(
                self.Folder,
                self.__DYN__.B_Version,
                "preset.blend",
            )
        )
