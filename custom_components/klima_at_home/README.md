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

## Was die Zahlen bedeuten

### Dürre zeigt „Problem" statt „an"

Das ist nur die Beschriftung, kein Fehler. Der Sensor hat die `device_class: problem`, und solche
Binärsensoren beschriftet Home Assistant grundsätzlich mit **„Problem" / „OK"** statt mit *an/aus*.
**„Problem" heißt: es herrscht gerade Dürre.**

**Warum** er angegangen ist, steht im Attribut **`ausgeloest_durch`** — es nennt das Kriterium
beim Namen. Zwei Auslöser, die unabhängig voneinander greifen, weil sie Verschiedenes erfassen:

| Auslöser | Schwelle | Erfasst |
|---|---|---|
| **Tage ohne Regen** | ≥ 14 Tage | die spürbare, lange regenlose Serie |
| **SPI 30 Tage** | ≤ −1,0 | ein echtes Niederschlagsdefizit, auch wenn zwischendurch etwas fiel |

Deshalb kann „Dürre" angehen, obwohl gestern Regen gemeldet war: Ein Monat mit gelegentlichem
Nieselregen, aber weit unter dem Normalwert, ist eine Dürre — auch wenn „Tage ohne Regen" auf 0
steht. Umgekehrt sind zwei trockene Wochen nach einem nassen Monat noch keine.

### Tage ohne Regen

Ein **Trockentag ist ein Tag mit weniger als 1 mm Niederschlag** — die ETCCDI-Definition der
*consecutive dry days*, nicht „exakt 0 mm". Sonst würde schon 0,1 mm Niesel oder Taubeschlag die
Serie zurücksetzen, obwohl im Boden nichts ankommt. Erst ab 1 mm gilt der Tag als Regentag und der
Zähler springt auf 0.

Das Attribut **`trockener_als_in_prozent_der_jahre`** ordnet die laufende Serie jahreszeitlich ein:
14 trockene Tage sind im August normal, im November nicht.

### Niederschlag 30 / 90 Tage

Der **Anteil am Normalwert derselben Jahreszeit**, in Prozent. Es wird der Regen der letzten 30 bzw.
90 Tage summiert und mit dem verglichen, was in genau diesem Zeitfenster historisch normal fällt.

- **100 %** — ein ganz normaler Zeitraum
- **40 %** — nur 40 % der üblichen Menge, deutlich zu trocken
- **180 %** — 80 % mehr Regen als sonst

**Warum zwei Zeiträume:** 30 Tage zeigen die aktuelle Lage (Rasen, Beete, Oberboden), 90 Tage die
längerfristige — davon leben Bäume, und daraus entsteht die Grundwasserneubildung. Ein einzelner
Starkregen reißt die 30-Tage-Zahl wieder hoch, während die 90-Tage-Zahl unten bleibt: dann ist der
Boden nur oberflächlich nass, das Defizit aber nicht aufgeholt.

### SPI 30 / 90 Tage

Der **Standardized Precipitation Index**, der von der WMO als Standard anerkannte Dürreindex. Er
beantwortet die Frage: *Wie ungewöhnlich ist diese Regenmenge für diese Jahreszeit an diesem Ort?*
Dazu wird die aktuelle Summe gegen die Verteilung aller historischen Werte desselben Zeitfensters
gehalten und in Standardabweichungen ausgedrückt. Die gleiche Einordnung steht im Klartext im
Attribut `einordnung`.

| SPI | Einordnung |
|---|---|
| ≥ +1,5 | sehr feucht |
| +1,0 … +1,5 | feucht |
| −1,0 … +1,0 | normal |
| −1,5 … −1,0 | mäßige Dürre |
| −2,0 … −1,5 | schwere Dürre |
| ≤ −2,0 | extreme Dürre |

**Warum SPI zusätzlich zu den Prozentwerten?** Die Prozentzahl allein sagt nicht, ob eine Abweichung
außergewöhnlich *ist*. 50 % des Normalwerts sind im nassen Januar dramatisch, im ohnehin trockenen
August aber halb normal — der SPI rechnet das heraus, die Prozentzahl nicht. Dafür ist die
Prozentzahl sofort verständlich. Deshalb gibt es beide: eine zum Verstehen, eine zum Einordnen. Für
Automatisierungen ist der SPI die robustere Größe; **−1,0** ist die offizielle Dürre-Schwelle.

### Temperaturabweichung

Wie weit das heutige Tagesmittel über (oder unter) dem langjährigen Mittel **desselben Kalendertags**
im Zeitraum **1961–1990** liegt — dem WMO-Referenzzeitraum für Klimaanomalien. `+5,3 °C` heißt also
nicht „5 °C wärmer als gestern", sondern „5 °C wärmer, als dieser Tag im Mittel von 1961–1990 war".

Die Attribute `normal_1961_1990` und `tagesmittel_heute` zeigen beide Größen, aus denen sich die
Differenz ergibt — die Zahl bleibt damit nachprüfbar.

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
