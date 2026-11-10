##from checker.tests.InterfaceChecker import Interface # reenable with with availability of nested inlines. see interface checker

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import (
        AnonymityChecker,
        AutoAttestChecker,
        CheckStyleChecker,
        CreateFileChecker,
        CUnitChecker_v2,
        DejaGnu,
        DiffChecker,
        HaskellTestFrameWorkChecker,
        InterfaceChecker,
        IsabelleChecker,
        JavaChecker,
        JUnitChecker,
        KeepFileChecker,
        LineCounter,
        LineWidthChecker,
        RChecker,
        ScriptChecker,
        TextChecker,
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
