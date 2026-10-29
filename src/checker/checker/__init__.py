##from checker.tests.InterfaceChecker import Interface # reenable with with availability of nested inlines. see interface checker

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import (
        AnonymityChecker,
        InterfaceChecker,
        LineWidthChecker,
        TextChecker,
        ScriptChecker,
        CreateFileChecker,
        LineCounter,
        JUnitChecker,
        JavaChecker,
        DejaGnu,
        CheckStyleChecker,
        IsabelleChecker,
        HaskellTestFrameWorkChecker,
        RChecker,
        KeepFileChecker,
        CUnitChecker_v2,
        DiffChecker,
        AutoAttestChecker,
    )

__all__ = [    "AnonymityChecker",
            "InterfaceChecker", ##"Interface",
            "LineWidthChecker",
            "TextChecker",
            "ScriptChecker",
            "CreateFileChecker",
            "LineCounter",
            "JUnitChecker",
            "JavaChecker",
            "DejaGnu",
            "CheckStyleChecker",
            "IsabelleChecker",
            "HaskellTestFrameWorkChecker",
            "RChecker",
            "KeepFileChecker",
            "CUnitChecker_v2",
            "DiffChecker",
            "AutoAttestChecker",
          ]
