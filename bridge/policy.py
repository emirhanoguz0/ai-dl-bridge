"""Policy layer — v1 single rule: >2GB requires user approval.

Rules are stored in an extensible list; each rule is a function
returning Karar(uygun: bool, beklemede: bool, sebep: str).
"""
from dataclasses import dataclass

ONAY_LIMITI = 2 * 1024**3  # 2GB


@dataclass
class Karar:
    uygun: bool              # can be added to queue immediately
    beklemede: bool = False  # waiting for user approval
    sebep: str = ""          # reason if rejected or pending

    @property
    def approved(self) -> bool:
        return self.uygun

    @property
    def pending(self) -> bool:
        return self.beklemede

    @property
    def reason(self) -> str:
        return self.sebep


def boyut_kurali(bayt: int | None) -> Karar:
    if bayt is None:                      # unknown size → safe side, download
        return Karar(uygun=True)
    if bayt > ONAY_LIMITI:
        return Karar(False, True, f"{bayt/1024**3:.1f}GB > 2GB — user approval required")
    return Karar(uygun=True)


KURALLAR = [boyut_kurali]


def degerlendir(bayt: int | None) -> Karar:
    for kural in KURALLAR:
        k = kural(bayt)
        if not k.uygun or k.beklemede:
            return k
    return Karar(uygun=True)

