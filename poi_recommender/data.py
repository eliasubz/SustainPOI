from __future__ import annotations

from dataclasses import dataclass


INTERESTS = [
    "architecture",
    "religion",
    "food",
    "museums",
    "nature",
    "shopping",
    "nightlife",
    "beach",
    "history",
    "family",
]


@dataclass(frozen=True)
class POI:
    id: int
    name: str
    district: str
    neighbourhood: str
    lat: float
    lon: float
    tags: tuple[str, ...]
    popularity: float
    price: float
    duration: float
    capacity: int
    sustainability: float
    local_value: float
    cultural_value: float
    outdoor: bool
    family_friendly: bool
    accessibility: float
    open_hour: float
    close_hour: float

    @property
    def operating_hours(self):
        return max(1.0, self.close_hour - self.open_hour)


# Opening hours are simplified but plausible. They are used for two things:
#   1. feasibility (a tourist cannot visit a POI that is closed when they arrive), and
#   2. deriving an *instantaneous* concurrent capacity from the daily-throughput capacity.
# Exact, name-keyed overrides take priority; otherwise hours are assigned by category.
_HOUR_OVERRIDES = {
    "Magic Fountain": (19.0, 22.5),          # evening light-and-water show
    "Tibidabo Amusement Park": (11.0, 20.0),
    "Tibidabo Temple": (10.0, 18.0),
    "Bunkers del Carmel": (9.0, 21.5),        # popular for sunset
    "Gracia Squares": (8.0, 23.5),            # nightlife squares
    "Raval Street Art Route": (8.0, 22.0),
    "Poblenou Rambla": (7.5, 23.5),
}

_STREET_LIKE = {
    "La Rambla", "Gothic Quarter", "Passeig de Gracia", "Sant Andreu Old Town",
}
_MARKETS = {
    "Mercat de la Boqueria", "Mercat dels Encants", "Sant Antoni Market", "Sants Market",
}
_PARK_KEYWORDS = ("Beach", "Park", "Parc", "Viewpoints")


def _opening_hours(name, tags):
    if name in _HOUR_OVERRIDES:
        return _HOUR_OVERRIDES[name]
    if name in _STREET_LIKE:
        return (7.0, 23.0)
    if name in _MARKETS:
        return (8.0, 20.0)
    if "beach" in tags:
        return (8.0, 21.0)
    if any(keyword in name for keyword in _PARK_KEYWORDS):
        return (8.0, 20.5)
    if tags and tags[0] == "nature":
        return (8.0, 20.5)
    # Default: museums, monuments, religious and architectural sites.
    return (9.5, 19.5)


def load_barcelona_pois():
    raw = [
        ("Sagrada Familia", "Eixample", "Sagrada Familia", 41.4036, 2.1744, ("architecture", "religion", "history"), .99, 26, 2.0, 900, .45, .45, .98, False, True, .88),
        ("Casa Batllo", "Eixample", "Dreta de l'Eixample", 41.3917, 2.1649, ("architecture", "museums", "history"), .94, 35, 1.5, 550, .42, .40, .90, False, True, .85),
        ("La Pedrera", "Eixample", "Dreta de l'Eixample", 41.3954, 2.1619, ("architecture", "museums"), .90, 28, 1.5, 520, .46, .42, .88, False, True, .82),
        ("Park Guell", "Gracia", "La Salut", 41.4145, 2.1527, ("architecture", "nature", "family"), .92, 13, 2.0, 800, .62, .50, .86, True, True, .62),
        ("La Rambla", "Ciutat Vella", "Raval/Gotic", 41.3818, 2.1716, ("shopping", "food", "nightlife"), .88, 0, 1.0, 1200, .35, .55, .55, True, True, .92),
        ("Mercat de la Boqueria", "Ciutat Vella", "Raval", 41.3817, 2.1714, ("food", "shopping", "history"), .87, 0, 1.0, 700, .50, .82, .62, False, True, .90),
        ("Barcelona Cathedral", "Ciutat Vella", "Gotic", 41.3839, 2.1763, ("religion", "architecture", "history"), .84, 14, 1.2, 650, .50, .48, .90, False, True, .78),
        ("Gothic Quarter", "Ciutat Vella", "Gotic", 41.3830, 2.1760, ("history", "architecture", "nightlife"), .89, 0, 2.0, 1800, .44, .70, .86, True, True, .70),
        ("Picasso Museum", "Ciutat Vella", "Sant Pere", 41.3852, 2.1809, ("museums", "history"), .80, 14, 1.5, 480, .55, .52, .85, False, False, .83),
        ("Santa Maria del Mar", "Ciutat Vella", "Born", 41.3839, 2.1820, ("religion", "architecture", "history"), .76, 5, 0.8, 500, .58, .55, .89, False, True, .74),
        ("Parc de la Ciutadella", "Ciutat Vella", "Sant Pere", 41.3881, 2.1875, ("nature", "family", "history"), .74, 0, 1.5, 1300, .83, .56, .68, True, True, .88),
        ("Barceloneta Beach", "Ciutat Vella", "Barceloneta", 41.3784, 2.1925, ("beach", "nature", "nightlife"), .82, 0, 2.0, 1600, .57, .64, .45, True, True, .86),
        ("Palau de la Musica", "Ciutat Vella", "Sant Pere", 41.3875, 2.1753, ("architecture", "museums", "history"), .72, 18, 1.0, 400, .54, .46, .87, False, False, .80),
        ("Montjuic Castle", "Sants-Montjuic", "Montjuic", 41.3634, 2.1650, ("history", "nature", "family"), .66, 12, 1.5, 650, .70, .50, .78, True, True, .56),
        ("MNAC", "Sants-Montjuic", "Montjuic", 41.3688, 2.1535, ("museums", "history", "architecture"), .68, 12, 2.0, 600, .61, .48, .86, False, True, .72),
        ("Joan Miro Foundation", "Sants-Montjuic", "Montjuic", 41.3686, 2.1597, ("museums", "architecture"), .58, 15, 1.4, 350, .62, .45, .76, False, False, .75),
        ("Poble Espanyol", "Sants-Montjuic", "Font de la Guatlla", 41.3689, 2.1479, ("history", "food", "family"), .62, 14, 2.0, 700, .60, .75, .65, True, True, .82),
        ("Magic Fountain", "Sants-Montjuic", "Font de la Guatlla", 41.3712, 2.1517, ("family", "nightlife", "architecture"), .73, 0, 1.0, 1500, .49, .48, .50, True, True, .90),
        ("Camp Nou Museum", "Les Corts", "La Maternitat", 41.3809, 2.1228, ("museums", "family", "shopping"), .77, 28, 1.5, 750, .38, .43, .48, False, True, .88),
        ("Pedralbes Monastery", "Les Corts", "Pedralbes", 41.3958, 2.1128, ("religion", "history", "architecture"), .36, 5, 1.2, 260, .72, .62, .80, False, False, .70),
        ("Tibidabo Temple", "Sarria-Sant Gervasi", "Vallvidrera", 41.4225, 2.1186, ("religion", "architecture", "nature"), .55, 0, 1.2, 420, .78, .58, .80, True, True, .40),
        ("Tibidabo Amusement Park", "Sarria-Sant Gervasi", "Vallvidrera", 41.4217, 2.1192, ("family", "nature"), .63, 35, 3.0, 800, .58, .54, .45, True, True, .45),
        ("CosmoCaixa", "Sarria-Sant Gervasi", "Sant Gervasi", 41.4133, 2.1315, ("museums", "family"), .61, 6, 2.0, 600, .70, .50, .58, False, True, .85),
        ("Bunkers del Carmel", "Horta-Guinardo", "El Carmel", 41.4186, 2.1619, ("nature", "history", "nightlife"), .65, 0, 1.0, 500, .66, .42, .60, True, False, .32),
        ("Hospital Sant Pau", "Horta-Guinardo", "Guinardo", 41.4122, 2.1744, ("architecture", "history", "museums"), .64, 17, 1.3, 450, .64, .52, .84, False, True, .78),
        ("Labyrinth Park of Horta", "Horta-Guinardo", "Horta", 41.4390, 2.1458, ("nature", "family", "history"), .32, 3, 1.3, 350, .88, .64, .58, True, True, .52),
        ("Mercat dels Encants", "Sant Marti", "Fort Pienc", 41.4031, 2.1873, ("shopping", "food", "history"), .43, 0, 1.0, 650, .78, .88, .50, True, True, .86),
        ("Design Museum", "Sant Marti", "Fort Pienc", 41.4025, 2.1877, ("museums", "architecture"), .45, 6, 1.2, 330, .70, .55, .62, False, False, .90),
        ("Poblenou Rambla", "Sant Marti", "Poblenou", 41.4004, 2.2035, ("food", "shopping", "nightlife"), .40, 0, 1.4, 700, .68, .84, .45, True, True, .88),
        ("Bogatell Beach", "Sant Marti", "Poblenou", 41.3912, 2.2045, ("beach", "nature", "family"), .47, 0, 2.0, 1200, .72, .58, .35, True, True, .88),
        ("Can Framis Museum", "Sant Marti", "Poblenou", 41.4045, 2.1963, ("museums", "history"), .24, 8, 1.2, 220, .73, .62, .55, False, False, .80),
        ("Sant Antoni Market", "Eixample", "Sant Antoni", 41.3789, 2.1607, ("food", "shopping", "history"), .49, 0, 1.0, 700, .76, .90, .56, False, True, .90),
        ("Passeig de Gracia", "Eixample", "Dreta de l'Eixample", 41.3925, 2.1647, ("shopping", "architecture"), .83, 0, 1.5, 1600, .43, .62, .62, True, True, .94),
        ("Gracia Squares", "Gracia", "Vila de Gracia", 41.4034, 2.1586, ("food", "nightlife", "history"), .48, 0, 1.4, 750, .71, .86, .58, True, True, .82),
        ("Casa Vicens", "Gracia", "Vila de Gracia", 41.4036, 2.1506, ("architecture", "museums", "history"), .46, 21, 1.1, 270, .62, .50, .80, False, False, .72),
        ("El Born Cultural Centre", "Ciutat Vella", "Born", 41.3854, 2.1835, ("history", "museums", "food"), .50, 0, 1.0, 500, .75, .72, .72, False, True, .88),
        ("Maritime Museum", "Ciutat Vella", "Raval", 41.3769, 2.1745, ("museums", "history", "family"), .38, 10, 1.4, 390, .68, .54, .64, False, True, .82),
        ("History Museum of Catalonia", "Ciutat Vella", "Barceloneta", 41.3803, 2.1854, ("museums", "history", "family"), .42, 6, 1.3, 350, .72, .64, .76, False, True, .86),
        ("Palau Guell", "Ciutat Vella", "Raval", 41.3788, 2.1740, ("architecture", "history", "museums"), .51, 12, 1.0, 260, .60, .50, .75, False, False, .70),
        ("Recinte Fabra i Coats", "Sant Andreu", "Sant Andreu", 41.4339, 2.1901, ("museums", "history", "family"), .20, 0, 1.0, 300, .84, .82, .56, False, True, .80),
        ("Sant Andreu Old Town", "Sant Andreu", "Sant Andreu", 41.4350, 2.1905, ("history", "food", "shopping"), .22, 0, 1.3, 600, .80, .86, .52, True, True, .78),
        ("Nou Barris Central Park", "Nou Barris", "La Guineueta", 41.4419, 2.1687, ("nature", "family"), .18, 0, 1.2, 700, .90, .72, .36, True, True, .86),
        ("Turo de la Peira Park", "Nou Barris", "Turo de la Peira", 41.4319, 2.1660, ("nature", "family"), .16, 0, 1.0, 500, .88, .66, .32, True, True, .58),
        ("Sants Market", "Sants-Montjuic", "Sants", 41.3753, 2.1360, ("food", "shopping"), .30, 0, 1.0, 500, .78, .88, .40, False, True, .86),
        ("Can Batllo", "Sants-Montjuic", "La Bordeta", 41.3695, 2.1338, ("history", "museums", "family"), .18, 0, 1.0, 280, .86, .84, .48, True, True, .68),
        ("Collserola Viewpoints", "Sarria-Sant Gervasi", "Collserola", 41.4269, 2.1005, ("nature", "family"), .28, 0, 2.0, 650, .93, .52, .34, True, True, .35),
        ("MUHBA Placa del Rei", "Ciutat Vella", "Gotic", 41.3849, 2.1772, ("museums", "history"), .44, 7, 1.2, 300, .70, .54, .80, False, False, .74),
        ("Raval Street Art Route", "Ciutat Vella", "Raval", 41.3802, 2.1697, ("history", "nightlife", "shopping"), .34, 0, 1.0, 500, .74, .82, .46, True, False, .76),
        ("El Clot Park", "Sant Marti", "El Clot", 41.4101, 2.1885, ("nature", "family", "history"), .21, 0, 1.0, 550, .88, .66, .42, True, True, .88),
        ("Forum Park", "Sant Marti", "Diagonal Mar", 41.4117, 2.2269, ("beach", "nature", "family"), .31, 0, 1.4, 1000, .76, .55, .30, True, True, .82),
        ("Diagonal Mar Park", "Sant Marti", "Diagonal Mar", 41.4075, 2.2165, ("nature", "family"), .29, 0, 1.2, 800, .86, .62, .34, True, True, .88),
    ]
    pois = []
    for i, row in enumerate(raw):
        name, tags = row[0], row[5]
        open_hour, close_hour = _opening_hours(name, tags)
        pois.append(POI(i, *row, open_hour=open_hour, close_hour=close_hour))
    return pois
