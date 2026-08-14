# plugins/element_constants/data.py
"""
元素・物理定数テーブル(項目P-805)のデータ本体。GUI(PySide6)に一切依存しない
プレーンなPythonモジュールとして分離してあり、単体テストが容易なだけでなく、
「他パックの共通基盤」(docs/Graphica_PLUGIN_BACKLOG.md)として他のプラグインが
そのままimportして再利用できるようにしている。

周期表データ(原子番号・元素記号・英語名・原子量)は、mendeleev/periodictable等の
外部パッケージがGraphica同梱パッケージ一覧(numpy/pandas/scipy/matplotlib/PySide6/
openpyxl)に含まれておらず、プラグインのrequires規約(同梱パッケージのみ許可)上
追加できないため、ここに自前で同梱する。安定同位体を持たない元素の原子量は、
最も安定な同位体の質量数を整数値として掲載する(IUPAC慣行に倣う)。

物理定数はscipy.constants.physical_constants(CODATA値、同梱済み)をそのまま
再利用し、値を手で転記しない。
"""
import scipy.constants as _scipy_constants

# (原子番号, 元素記号, 英語名, 原子量[g/mol]) — 原子量はIUPAC標準原子量(2021)に基づく
# 概数。安定同位体を持たない元素は最も安定な同位体の質量数(整数)。
_ELEMENT_ROWS = [
    (1, "H", "Hydrogen", 1.008),
    (2, "He", "Helium", 4.0026),
    (3, "Li", "Lithium", 6.94),
    (4, "Be", "Beryllium", 9.0122),
    (5, "B", "Boron", 10.81),
    (6, "C", "Carbon", 12.011),
    (7, "N", "Nitrogen", 14.007),
    (8, "O", "Oxygen", 15.999),
    (9, "F", "Fluorine", 18.998),
    (10, "Ne", "Neon", 20.180),
    (11, "Na", "Sodium", 22.990),
    (12, "Mg", "Magnesium", 24.305),
    (13, "Al", "Aluminium", 26.982),
    (14, "Si", "Silicon", 28.085),
    (15, "P", "Phosphorus", 30.974),
    (16, "S", "Sulfur", 32.06),
    (17, "Cl", "Chlorine", 35.45),
    (18, "Ar", "Argon", 39.948),
    (19, "K", "Potassium", 39.098),
    (20, "Ca", "Calcium", 40.078),
    (21, "Sc", "Scandium", 44.956),
    (22, "Ti", "Titanium", 47.867),
    (23, "V", "Vanadium", 50.942),
    (24, "Cr", "Chromium", 51.996),
    (25, "Mn", "Manganese", 54.938),
    (26, "Fe", "Iron", 55.845),
    (27, "Co", "Cobalt", 58.933),
    (28, "Ni", "Nickel", 58.693),
    (29, "Cu", "Copper", 63.546),
    (30, "Zn", "Zinc", 65.38),
    (31, "Ga", "Gallium", 69.723),
    (32, "Ge", "Germanium", 72.630),
    (33, "As", "Arsenic", 74.922),
    (34, "Se", "Selenium", 78.971),
    (35, "Br", "Bromine", 79.904),
    (36, "Kr", "Krypton", 83.798),
    (37, "Rb", "Rubidium", 85.468),
    (38, "Sr", "Strontium", 87.62),
    (39, "Y", "Yttrium", 88.906),
    (40, "Zr", "Zirconium", 91.224),
    (41, "Nb", "Niobium", 92.906),
    (42, "Mo", "Molybdenum", 95.95),
    (43, "Tc", "Technetium", 98),
    (44, "Ru", "Ruthenium", 101.07),
    (45, "Rh", "Rhodium", 102.91),
    (46, "Pd", "Palladium", 106.42),
    (47, "Ag", "Silver", 107.87),
    (48, "Cd", "Cadmium", 112.41),
    (49, "In", "Indium", 114.82),
    (50, "Sn", "Tin", 118.71),
    (51, "Sb", "Antimony", 121.76),
    (52, "Te", "Tellurium", 127.60),
    (53, "I", "Iodine", 126.90),
    (54, "Xe", "Xenon", 131.29),
    (55, "Cs", "Caesium", 132.91),
    (56, "Ba", "Barium", 137.33),
    (57, "La", "Lanthanum", 138.91),
    (58, "Ce", "Cerium", 140.12),
    (59, "Pr", "Praseodymium", 140.91),
    (60, "Nd", "Neodymium", 144.24),
    (61, "Pm", "Promethium", 145),
    (62, "Sm", "Samarium", 150.36),
    (63, "Eu", "Europium", 151.96),
    (64, "Gd", "Gadolinium", 157.25),
    (65, "Tb", "Terbium", 158.93),
    (66, "Dy", "Dysprosium", 162.50),
    (67, "Ho", "Holmium", 164.93),
    (68, "Er", "Erbium", 167.26),
    (69, "Tm", "Thulium", 168.93),
    (70, "Yb", "Ytterbium", 173.05),
    (71, "Lu", "Lutetium", 174.97),
    (72, "Hf", "Hafnium", 178.49),
    (73, "Ta", "Tantalum", 180.95),
    (74, "W", "Tungsten", 183.84),
    (75, "Re", "Rhenium", 186.21),
    (76, "Os", "Osmium", 190.23),
    (77, "Ir", "Iridium", 192.22),
    (78, "Pt", "Platinum", 195.08),
    (79, "Au", "Gold", 196.97),
    (80, "Hg", "Mercury", 200.59),
    (81, "Tl", "Thallium", 204.38),
    (82, "Pb", "Lead", 207.2),
    (83, "Bi", "Bismuth", 208.98),
    (84, "Po", "Polonium", 209),
    (85, "At", "Astatine", 210),
    (86, "Rn", "Radon", 222),
    (87, "Fr", "Francium", 223),
    (88, "Ra", "Radium", 226),
    (89, "Ac", "Actinium", 227),
    (90, "Th", "Thorium", 232.04),
    (91, "Pa", "Protactinium", 231.04),
    (92, "U", "Uranium", 238.03),
    (93, "Np", "Neptunium", 237),
    (94, "Pu", "Plutonium", 244),
    (95, "Am", "Americium", 243),
    (96, "Cm", "Curium", 247),
    (97, "Bk", "Berkelium", 247),
    (98, "Cf", "Californium", 251),
    (99, "Es", "Einsteinium", 252),
    (100, "Fm", "Fermium", 257),
    (101, "Md", "Mendelevium", 258),
    (102, "No", "Nobelium", 259),
    (103, "Lr", "Lawrencium", 266),
    (104, "Rf", "Rutherfordium", 267),
    (105, "Db", "Dubnium", 268),
    (106, "Sg", "Seaborgium", 269),
    (107, "Bh", "Bohrium", 270),
    (108, "Hs", "Hassium", 269),
    (109, "Mt", "Meitnerium", 278),
    (110, "Ds", "Darmstadtium", 281),
    (111, "Rg", "Roentgenium", 282),
    (112, "Cn", "Copernicium", 285),
    (113, "Nh", "Nihonium", 286),
    (114, "Fl", "Flerovium", 289),
    (115, "Mc", "Moscovium", 290),
    (116, "Lv", "Livermorium", 293),
    (117, "Ts", "Tennessine", 294),
    (118, "Og", "Oganesson", 294),
]

# atomic_number/symbol(大文字小文字を無視)の両方から即座に引けるよう、
# 2つの辞書を用意する(検索側は常にこの2つだけを見ればよい)。
ELEMENTS_BY_NUMBER = {row[0]: row for row in _ELEMENT_ROWS}
ELEMENTS_BY_SYMBOL = {row[1].lower(): row for row in _ELEMENT_ROWS}
ELEMENTS_BY_NAME = {row[2].lower(): row for row in _ELEMENT_ROWS}

ELEMENT_COLUMNS = ["原子番号", "元素記号", "英語名", "原子量"]


def find_element(query):
    """
    元素記号(H, he, FE...)・原子番号(数字)・英語名(部分一致)のいずれかで
    検索し、(原子番号, 記号, 英語名, 原子量) のタプルのリストを返す
    (完全一致が無ければ英語名の部分一致を候補として返す)。
    見つからなければ空リスト。
    """
    query = query.strip()
    if not query:
        return []

    if query.isdigit():
        row = ELEMENTS_BY_NUMBER.get(int(query))
        return [row] if row else []

    lowered = query.lower()
    exact = ELEMENTS_BY_SYMBOL.get(lowered) or ELEMENTS_BY_NAME.get(lowered)
    if exact:
        return [exact]

    return [row for row in _ELEMENT_ROWS if lowered in row[2].lower()]


# --- 物理定数(scipy.constants.physical_constants、CODATA値をそのまま利用) ---

# scipy.constants.physical_constants は445件と数が多く、大半は原子物理の
# 専門的な定数のため、名前検索(部分一致)は全件対象にしつつ、初期表示・
# よく使う定数のショートカットとして代表的なものだけキーワードを用意する。
COMMON_CONSTANT_KEYWORDS = {
    "光速": "speed of light in vacuum",
    "プランク定数": "Planck constant",
    "電気素量": "elementary charge",
    "アボガドロ数": "Avogadro constant",
    "ボルツマン定数": "Boltzmann constant",
    "気体定数": "molar gas constant",
    "万有引力定数": "Newtonian constant of gravitation",
    "電子質量": "electron mass",
    "陽子質量": "proton mass",
    "中性子質量": "neutron mass",
    "真空の誘電率": "vacuum electric permittivity",
    "真空の透磁率": "vacuum mag. permeability",
    "リュードベリ定数": "Rydberg constant",
    "ステファン・ボルツマン定数": "Stefan-Boltzmann constant",
    "ファラデー定数": "Faraday constant",
    "微細構造定数": "fine-structure constant",
}

CONSTANT_COLUMNS = ["名称", "値", "単位", "標準不確かさ"]


def find_constant(query):
    """
    物理定数を検索する。COMMON_CONSTANT_KEYWORDSの日本語キーワード完全一致を
    優先し、無ければscipy.constants.physical_constants全件から名称の部分一致
    (大文字小文字を無視)で検索する。戻り値は(名称, 値, 単位, 標準不確かさ)の
    タプルのリスト。
    """
    query = query.strip()
    if not query:
        return []

    mapped_name = COMMON_CONSTANT_KEYWORDS.get(query)
    if mapped_name is not None:
        value, unit, uncertainty = _scipy_constants.physical_constants[mapped_name]
        return [(mapped_name, value, unit, uncertainty)]

    lowered = query.lower()
    results = []
    for name, (value, unit, uncertainty) in _scipy_constants.physical_constants.items():
        if lowered in name.lower():
            results.append((name, value, unit, uncertainty))
    return results
