# Klima @ Home

Richte **einen Ort** ein und bekomme Entitäten für dein Dashboard und deine Automatisierungen:
lokales Wetter, wie ungewöhnlich warm es gerade ist, wie trocken es geworden ist — und wie es um
das Grundwasser in deiner Nähe steht.

## Was du bekommst

### Gerät „Wetter *Ort*"

| Entität | Beispiel | Bedeutung |
|---|---|---|
| `weather.*` | `partlycloudy`, 23,7 °C | Zustand, Temperatur, Luftfeuchte, Wind + **7-Tage-Vorhersage** |
| Temperatur / Luftfeuchte | 23,7 °C · 63 % | für direktes Binding im Dashboard |
| **Temperaturabweichung** | **+5,3 °C** | wie weit über (oder unter) dem langjährigen Mittel **1961–1990** der heutige Tag liegt |
| **Tage ohne Regen** | 0 d | aktuelle Trockenperiode |
| **Niederschlag 30 / 90 Tage** | 45 % · 74 % | Anteil am Normalwert derselben Jahreszeit |
| **SPI 30 / 90 Tage** | −1,47 → *mäßige Dürre* | der von der WMO anerkannte Dürre-Index |
| **Dürre** (binär) | `an` | für Automatisierungen |

### Gerät „Grundwasser *Messstelle*" (×3, nur in Deutschland)

| Entität | Beispiel |
|---|---|
| **Einordnung** | `sehr_niedrig` · `niedrig` · `normal` · `hoch` · `sehr_hoch` |
| **Kritisch** (binär) | `an`, wenn die BGR den Stand als „sehr niedrig" einstuft |
| **Prognose 4 Wochen** | wohin es laut BGR-Modell geht |
| **Trend 4 Wochen** | `stark_fallend` … `stark_steigend` |

## Einrichtung

**Einstellungen → Geräte & Dienste → Integration hinzufügen → Klima @ Home.**
Ort auf der Karte wählen (voreingestellt: dein Zuhause), fertig.

Beim ersten Start lädt die Integration einmalig 30 Jahre Klimadaten (1961–1990) für deinen Ort.
Das dauert einen Moment und passiert **genau ein Mal** — danach liegt es im Cache, ein Neustart
löst es nicht erneut aus.

## Was du wissen solltest

### Grundwasser gibt es nur als Einordnung, nicht in Metern

Das ist keine Auslassung, sondern die Datenlage in Deutschland. Die BGR veröffentlicht über
[GRUVO](https://gruvo.bgr.de/website/mapapp) für **4.390 Messstellen bundesweit** die amtliche
Einstufung — aber **keinen Pegelstand in Metern**. Von 16 Bundesländern erlauben laut
Umweltbundesamt nur **Berlin, NRW und Schleswig-Holstein** überhaupt einen automatisierten Abruf
der Rohmesswerte; Bayern und Baden-Württemberg etwa bieten gar keine Schnittstelle.

Diese Integration meldet deshalb die amtliche Klasse und **erfindet keine Zahl**. Es gibt also auch
keine Pegel-Kurve — wohl aber den Verlauf der Einordnung, den Home Assistant ab Installation
aufzeichnet. (GRUVO schreibt die Daten ohnehin nur **monatlich** fort; eine Tageskurve gäbe es dort
so oder so nicht.)

Die Klassen sind Perzentile gegen den Referenzzeitraum **1991–2020** — dieselbe Skala, die die
Fachbehörden verwenden:

| Klasse | Bedeutung |
|---|---|
| sehr niedrig | unter dem 10. Perzentil |
| niedrig | 10.–25. Perzentil |
| normal | 25.–75. Perzentil |
| hoch | 75.–90. Perzentil |
| sehr hoch | über dem 90. Perzentil |

Die BGR weist ausdrücklich darauf hin, dass „sehr niedrig" eine **statistische** Aussage ist und
kein ausgerufener Wassernotstand.

### Wetter funktioniert weltweit, Grundwasser nur in Deutschland

Für Orte außerhalb Deutschlands entstehen die Wetter-, Klima- und Dürre-Entitäten ganz normal —
das Grundwasser-Gerät entfällt einfach.

### Warum „Dürre" angehen kann, obwohl es gestern geregnet hat

Zwei unabhängige Kriterien lösen aus, weil sie Verschiedenes erfassen: eine **lange regenlose
Serie** (was man merkt) und ein **echtes Niederschlagsdefizit** über 30 Tage (was Pflanzen und
Grundwasser merken). Ein Monat mit gelegentlichem Nieselregen, aber weit unter dem Normalwert, ist
eine Dürre — auch wenn „Tage ohne Regen" auf 0 steht.

Ein Trockentag ist übrigens ein Tag mit **weniger als 1 mm** Niederschlag (ETCCDI-Definition), nicht
mit exakt 0 mm — sonst würde jeder Taubeschlag die Serie zurücksetzen.

## Beispiel-Automatisierung

```yaml
automation:
  - alias: "Warnung bei kritischem Grundwasser"
    trigger:
      - platform: state
        entity_id: binary_sensor.grundwasser_wettesingen_kritisch
        to: "on"
    action:
      - service: notify.persistent_notification
        data:
          message: >
            Grundwasser an der Messstelle Wettesingen ist laut BGR
            "sehr niedrig" ({{ state_attr('sensor.grundwasser_wettesingen_einordnung',
            'entfernung_km') }} km entfernt).
```

## Datenquellen

- **Wetter, Klima, Dürre:** [Open-Meteo](https://open-meteo.com/) (ERA5-Reanalyse), kostenlos, ohne
  API-Schlüssel.
- **Grundwasser:** [BGR GRUVO](https://gruvo.bgr.de/website/mapapp).

## Entwicklung

```bash
python3.13 -m venv .venv-test
.venv-test/bin/pip install homeassistant pytest pytest-asyncio pytest-homeassistant-custom-component

# Rechenlogik (offline, schnell)
.venv-test/bin/python -m pytest tests/ -m "not live"

# End-to-End in echtem Home Assistant gegen die echten APIs
.venv-test/bin/python -m pytest tests/ -m live

# Prüfen, ob die externen APIs noch so antworten wie angenommen
python3 scripts/verify_apis.py
```
