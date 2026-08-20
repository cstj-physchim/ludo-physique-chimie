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
            "A1": "violet_1.png", "A2": "violet_2.png", "A3": "violet_3.png", "A4": "violet_4.png",
            "A5": "violet_5.png", "A6": "violet_6.png", "A7": "violet_7.png", "A8": "violet_8.png",
            "A9": "violet_9.png", "A10": "violet_10.png", "A11": "violet_11.png", "A12": "violet_12.png",
            "A13": "violet_13.png", "A14": "violet_14.png", "A15": "violet_15.png", "A16": "violet_16.png",
        },
    },
    "Jaune": {
        "emoji": "🟡",
        "theme": "Électricité",
        "order": ["A1","A10","A16","A12","A6","A8","A7","A15","A11","A5","A3","A2","A13","A14","A4","A9"],
        "dominos": {
            "A1": "jaune_1.png", "A2": "jaune_2.png", "A3": "jaune_3.png", "A4": "jaune_4.png",
            "A5": "jaune_5.png", "A6": "jaune_6.png", "A7": "jaune_7.png", "A8": "jaune_8.png",
            "A9": "jaune_9.png", "A10": "jaune_10.png", "A11": "jaune_11.png", "A12": "jaune_12.png",
            "A13": "jaune_13.png", "A14": "jaune_14.png", "A15": "jaune_15.png", "A16": "jaune_16.png",
        },
    },
    "Vert": {
        "emoji": "🟢",
        "theme": "Électricité",
        "order": ["A1","A11","A7","A9","A6","A4","A13","A10","A5","A2","A16","A12","A3","A15","A14","A8"],
        "dominos": {
            "A1": "vert_1.png", "A2": "vert_2.png", "A3": "vert_3.png", "A4": "vert_4.png",
            "A5": "vert_5.png", "A6": "vert_6.png", "A7": "vert_7.png", "A8": "vert_8.png",
            "A9": "vert_9.png", "A10": "vert_10.png", "A11": "vert_11.png", "A12": "vert_12.png",
            "A13": "vert_13.png", "A14": "vert_14.png", "A15": "vert_15.png", "A16": "vert_16.png",
        },
    },
    "Bleu": {
        "emoji": "🔵",
        "theme": "Électricité",
        "order": ["A1","A6","A13","A2","A11","A3","A12","A4","A15","A9","A7","A5","A10","A16","A14","A8"],
        "dominos": {
            "A1": "bleu_1.png", "A2": "bleu_2.png", "A3": "bleu_3.png", "A4": "bleu_4.png",
            "A5": "bleu_5.png", "A6": "bleu_6.png", "A7": "bleu_7.png", "A8": "bleu_8.png",
            "A9": "bleu_9.png", "A10": "bleu_10.png", "A11": "bleu_11.png", "A12": "bleu_12.png",
            "A13": "bleu_13.png", "A14": "bleu_14.png", "A15": "bleu_15.png", "A16": "bleu_16.png",
        },
    },
    "Orange": {
        "emoji": "🟠",
        "theme": "Électricité",
        "order": ["A1","A5","A13","A9","A4","A10","A16","A11","A14","A12","A2","A6","A3","A8","A7","A15"],
        "dominos": {
            "A1": "orange_1.png", "A2": "orange_2.png", "A3": "orange_3.png", "A4": "orange_4.png",
            "A5": "orange_5.png", "A6": "orange_6.png", "A7": "orange_7.png", "A8": "orange_8.png",
            "A9": "orange_9.png", "A10": "orange_10.png", "A11": "orange_11.png", "A12": "orange_12.png",
            "A13": "orange_13.png", "A14": "orange_14.png", "A15": "orange_15.png", "A16": "orange_16.png",
        },
    },
    "Rouge": {
        "emoji": "🔴",
        "theme": "Électricité",
        "order": ["A1","A2","A13","A4","A14","A15","A5","A7","A9","A12","A11","A16","A3","A8","A6","A10"],
        "dominos": {
            "A1": "rouge_1.png", "A2": "rouge_2.png", "A3": "rouge_3.png", "A4": "rouge_4.png",
            "A5": "rouge_5.png", "A6": "rouge_6.png", "A7": "rouge_7.png", "A8": "rouge_8.png",
            "A9": "rouge_9.png", "A10": "rouge_10.png", "A11": "rouge_11.png", "A12": "rouge_12.png",
            "A13": "rouge_13.png", "A14": "rouge_14.png", "A15": "rouge_15.png", "A16": "rouge_16.png",
        },
    },
}

MOLECULE_LEVEL_NAMES = ["Facile", "Moyen", "Difficile", "Très difficile"]
ELECTRICITY_LEVEL_NAMES = ["Violet", "Jaune", "Vert", "Bleu", "Orange", "Rouge"]

# Compatibilité avec le code plus ancien
LEVEL_NAMES = MOLECULE_LEVEL_NAMES
