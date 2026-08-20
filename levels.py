LEVELS = {
    "Facile": {
        "emoji": "🟢",
        "theme": "Molécules",
        "order": ["A1","A6","A11","A10","A8","A9","A12","A7","A3","A14","A2","A13","A5","A4"],
        "dominos": {
            "A1": ("h2","O₂"), "A6": ("o2","2 C"), "A11": ("2c","CH₄"), "A10": ("ch4","N₂"),
            "A8": ("n2","2 H"), "A9": ("2h","H₂O"), "A12": ("h2o","CO₂"), "A7": ("co2","C + O₂"),
            "A3": ("c_plus_o2","N + O₂"), "A14": ("n_plus_o2","H₂ + O"), "A2": ("h2_plus_o","CO"),
            "A13": ("co","NO₂"), "A5": ("no2","2 N"), "A4": ("2n","H₂"),
        },
    },
    "Moyen": {
        "emoji": "🟡",
        "theme": "Molécules",
        "order": ["A1","A4","A12","A2","A9","A8","A3","A7","A13","A5","A11","A14","A6","A10"],
        "dominos": {
            "A1": ("4h2","2 CO₂"), "A4": ("2co2","2 CH₄"), "A12": ("2ch4","2 O + 2 H₂"),
            "A2": ("2o_plus_2h2","2 C₂H₆"), "A9": ("2c2h6","3 O₂"), "A8": ("3o2","2 H₂O"),
            "A3": ("2h2o","3 N₂"), "A7": ("3n2","SO₂"), "A13": ("so2","CO + H₂"),
            "A5": ("co_plus_h2","NH₃"), "A11": ("nh3","2 O₃"), "A14": ("2o3","S + O₂"),
            "A6": ("s_plus_o2","CO + 2 H"), "A10": ("co_plus_2h","4 H₂"),
        },
    },
    "Difficile": {
        "emoji": "🟠",
        "theme": "Molécules",
        "order": ["A1","A7","A11","A10","A3","A8","A5","A2","A4","A6","A12","A9","A14","A13"],
        "dominos": {
            "A1": ("2cl2","C₂H₆O"), "A7": ("c2h6o","2 NH₃ + O₂"),
            "A11": ("2nh3_plus_o2","2 CH₄ + O₂"), "A10": ("2ch4_plus_o2","2 NO₂ + S"),
            "A3": ("2no2_plus_s","4 Cl"), "A8": ("4cl","2 H₂ + 2 C + H₂O"),
            "A5": ("2h2_plus_2c_plus_h2o","2 C + O₃"), "A2": ("2c_plus_o3","N₂ + 2 HCl"),
            "A4": ("n2_plus_2hcl","N₂ + 2 H + 2 H₂"), "A6": ("n2_plus_2h_plus_2h2","2 SO₂ + CO₂"),
            "A12": ("2so2_plus_co2","C₄H₁₀"), "A9": ("c4h10","2 NO₂ + Cl₂"),
            "A14": ("2no2_plus_cl2","CO₂ + CO"), "A13": ("co2_plus_co","2 Cl₂"),
        },
    },
    "Très difficile": {
        "emoji": "🔴",
        "theme": "Molécules",
        "order": ["A1","A3","A9","A7","A12","A8","A6","A11","A2","A5","A13","A14","A10","A4"],
        "dominos": {
            "A1": ("2h_plus_2c_plus_o_plus_o3_plus_h2","C + 2 H₂O + CO₂"),
            "A3": ("c_plus_2h2o_plus_co2","2 CO + 2 H₂O"),
            "A9": ("2co_plus_2h2o","CO + CO₂ + H₂O + H₂"),
            "A7": ("co_plus_co2_plus_h2o_plus_h2","2 H + O + H₂ + C₂ + O₃"),
            "A12": ("2h_plus_o_plus_h2_plus_c2_plus_o3","CO + 2 H + CO₂ + H₂O"),
            "A8": ("co_plus_2h_plus_co2_plus_h2o","C₂ + O₂ + 2 H₂O"),
            "A6": ("c2_plus_o2_plus_2h2o","C + H₂O + 2 H + O + CO₂"),
            "A11": ("c_plus_h2o_plus_2h_plus_o_plus_co2","CO + H₂O + H + H₂ + O₂"),
            "A2": ("co_plus_h2o_plus_h_plus_h2_plus_o2","CO₂ + 2 H₂ + C + O₂"),
            "A5": ("co2_plus_2h2_plus_c_plus_o2","4 O + 2 C + 4 H"),
            "A13": ("4o_plus_2c_plus_4h","H₂ + 2 H + 2 CO₂"),
            "A14": ("h2_plus_2h_plus_2co2","CO₂ + H₂ + 2 H + O₂"),
            "A10": ("co2_plus_h2_plus_2h_plus_o2","2 C + 3 O + H₂O + 2 H"),
            "A4": ("2c_plus_3o_plus_h2o_plus_2h","2 H + 2 C + O + O₃ + H₂"),
        },
    },
    "Violet": {
        "emoji": "🟣",
        "theme": "Électricité",
        "order": ["A1","A15","A4","A5","A6","A12","A16","A9","A8","A10","A11","A7","A2","A13","A14","A3"],
        "dominos": {
            "A1": ("elec_violet_A1_montage", "img:elec_violet_A1_schema"),
            "A15": ("elec_violet_A15_montage", "img:elec_violet_A15_schema"),
            "A4": ("elec_violet_A4_montage", "img:elec_violet_A4_schema"),
            "A5": ("elec_violet_A5_montage", "img:elec_violet_A5_schema"),
            "A6": ("elec_violet_A6_montage", "img:elec_violet_A6_schema"),
            "A12": ("elec_violet_A12_montage", "img:elec_violet_A12_schema"),
            "A16": ("elec_violet_A16_montage", "img:elec_violet_A16_schema"),
            "A9": ("elec_violet_A9_montage", "img:elec_violet_A9_schema"),
            "A8": ("elec_violet_A8_montage", "img:elec_violet_A8_schema"),
            "A10": ("elec_violet_A10_montage", "img:elec_violet_A10_schema"),
            "A11": ("elec_violet_A11_montage", "img:elec_violet_A11_schema"),
            "A7": ("elec_violet_A7_montage", "img:elec_violet_A7_schema"),
            "A2": ("elec_violet_A2_montage", "img:elec_violet_A2_schema"),
            "A13": ("elec_violet_A13_montage", "img:elec_violet_A13_schema"),
            "A14": ("elec_violet_A14_montage", "img:elec_violet_A14_schema"),
            "A3": ("elec_violet_A3_montage", "img:elec_violet_A3_schema"),
        },
    },
}

MOLECULE_LEVEL_NAMES = ["Facile", "Moyen", "Difficile", "Très difficile"]
ELECTRICITY_LEVEL_NAMES = ["Violet"]

# Compatibilité avec le code plus ancien
LEVEL_NAMES = MOLECULE_LEVEL_NAMES
