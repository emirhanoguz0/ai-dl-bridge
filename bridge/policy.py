"""Politika katmanı — v1 tek kural: 2GB üstü onay bekler.

Kurallar genişletilebilir liste hâlindedir; her kural bir fonksiyondur ve
Karar(uygun: bool, beklemede: bool, sebep: str) döner.
"""
from dataclasses import dataclass

ONAY_LIMITI = 2 * 1024**3  # 2GB


@dataclass
class Karar:
    uygun: bool          # kuyruğa hemen eklenebilir mi
    beklemede: bool = False  # kullanıcı onayı bekliyor mu
    sebep: str = ""      # reddedildi/beklemede ise açıklama


def boyut_kurali(bayt: int | None) -> Karar:
    if bayt is None:                      # boyut bilinmiyor → güvenli tara, in
        return Karar(uygun=True)
    if bayt > ONAY_LIMITI:
        return Karar(False, True, f"{bayt/1024**3:.1f}GB > 2GB — kullanıcı onayı gerekli")
    return Karar(uygun=True)


KURALLAR = [boyut_kurali]


def degerlendir(bayt: int | None) -> Karar:
    for kural in KURALLAR:
        k = kural(bayt)
        if not k.uygun or k.beklemede:
            return k
    return Karar(uygun=True)
