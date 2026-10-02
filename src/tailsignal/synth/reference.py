"""Reference data for the synthetic generator.

All relative risks, prevalences, and behavior rates here are SYNTHETIC ASSUMPTIONS
chosen to be plausible, not estimates from literature. Real-data models (A, B) never
train on these values.
"""

# --- Markets: 3-digit ZIP prefixes (real prefixes, synthetic 5-digit completions) ---
MARKETS = {
    "PHL": {"zip3": ["190", "191", "194"], "weight": 0.40},
    "AUS": {"zip3": ["786", "787"], "weight": 0.35},
    "MSP": {"zip3": ["553", "554"], "weight": 0.25},
}

# --- Breeds ---
# canonical, species, group, size, prevalence weight, groom_need (0-1), text variants seen in source systems
BREEDS = [
    # dogs
    ("Labrador Retriever", "dog", "Sporting", "large", 10, 0.2, ["Lab", "Labrador", "LAB", "Labrador Retreiver", "Lab Retriever"]),
    ("Golden Retriever", "dog", "Sporting", "large", 7, 0.5, ["Golden", "Golden Ret.", "GOLDEN RETRIEVER", "Goldie"]),
    ("German Shepherd", "dog", "Herding", "large", 6, 0.3, ["GSD", "German Shepard", "Ger. Shepherd", "Alsatian"]),
    ("French Bulldog", "dog", "Non-Sporting", "small", 7, 0.1, ["Frenchie", "French Bull Dog", "FR BULLDOG"]),
    ("Bulldog", "dog", "Non-Sporting", "medium", 3, 0.1, ["English Bulldog", "British Bulldog", "Bull Dog"]),
    ("Poodle", "dog", "Non-Sporting", "medium", 4, 0.9, ["Standard Poodle", "Toy Poodle", "Mini Poodle", "POODLE"]),
    ("Goldendoodle", "dog", "Designer", "large", 6, 0.95, ["Golden Doodle", "Doodle", "Goldendoodle (F1B)", "Golden-doodle"]),
    ("Labradoodle", "dog", "Designer", "large", 3, 0.9, ["Labra Doodle", "Lab-doodle", "Labradoodle"]),
    ("Beagle", "dog", "Hound", "medium", 4, 0.1, ["BEAGLE", "Beagel"]),
    ("Dachshund", "dog", "Hound", "small", 4, 0.2, ["Doxie", "Weiner Dog", "Daschund", "Mini Dachshund"]),
    ("Rottweiler", "dog", "Working", "large", 3, 0.1, ["Rottie", "Rotweiler"]),
    ("Boxer", "dog", "Working", "large", 3, 0.1, ["BOXER", "Boxer Dog"]),
    ("Yorkshire Terrier", "dog", "Toy", "toy", 3, 0.8, ["Yorkie", "York. Terrier"]),
    ("Shih Tzu", "dog", "Toy", "toy", 3, 0.9, ["Shitzu", "Shih-Tzu", "Shihtzu"]),
    ("Cavalier King Charles Spaniel", "dog", "Toy", "small", 2, 0.5, ["Cavalier", "CKCS", "King Charles Spaniel"]),
    ("Siberian Husky", "dog", "Working", "large", 3, 0.5, ["Husky", "Sibe", "Siberian Huskey"]),
    ("Australian Shepherd", "dog", "Herding", "medium", 3, 0.5, ["Aussie", "Aus. Shepherd", "Australian Shepard"]),
    ("Border Collie", "dog", "Herding", "medium", 2, 0.4, ["Collie", "BC", "Border-Collie"]),
    ("Pit Bull Terrier", "dog", "Terrier", "medium", 5, 0.1, ["Pit Bull", "Pitbull", "APBT", "Pittie", "Am. Staffordshire"]),
    ("Chihuahua", "dog", "Toy", "toy", 3, 0.1, ["Chi", "CHIHUAHUA", "Chihuahau"]),
    ("Mixed Breed Dog", "dog", "Mixed", "medium", 12, 0.3, ["Mix", "Mixed", "Mutt", "Lab mix", "Shepherd mix", "Terrier X", "Unknown"]),
    # cats
    ("Domestic Shorthair", "cat", "Domestic", "cat", 18, 0.0, ["DSH", "Dom. Shorthair", "Domestic SH", "Tabby"]),
    ("Domestic Longhair", "cat", "Domestic", "cat", 4, 0.3, ["DLH", "Dom. Longhair", "Domestic LH"]),
    ("Maine Coon", "cat", "Pedigree", "cat", 2, 0.5, ["Maine Coone", "MaineCoon", "Coon cat"]),
    ("Siamese", "cat", "Pedigree", "cat", 1.5, 0.0, ["SIAMESE", "Siamese mix"]),
    ("Persian", "cat", "Pedigree", "cat", 1, 0.8, ["PERSIAN", "Persian Longhair"]),
    ("Ragdoll", "cat", "Pedigree", "cat", 1.5, 0.3, ["Rag Doll", "RAGDOLL"]),
]

# --- Conditions ---
# name, species ("dog"/"cat"/"both"), base annual hazard, age effect per year (log scale),
# acute(True)/chronic(False), notes signal type
CONDITIONS = {
    "allergic_dermatitis": ("both", 0.06, 0.00, False, "skin"),
    "otitis_externa":      ("dog",  0.07, 0.00, True,  "ear"),
    "gastroenteritis":     ("both", 0.10, -0.02, True, "gi"),
    "dental_disease":      ("both", 0.05, 0.12, False, "dental"),
    "osteoarthritis":      ("both", 0.015, 0.22, False, "mobility"),
    "cruciate_injury":     ("dog",  0.008, 0.08, True,  "mobility"),
    "ivdd":                ("dog",  0.003, 0.10, True,  "mobility"),
    "mass_neoplasia":      ("both", 0.006, 0.25, False, "lump"),
    "mitral_valve_disease": ("dog", 0.004, 0.25, False, "lethargy"),
    "chronic_kidney_disease": ("cat", 0.008, 0.28, False, "lethargy"),
    "hypertrophic_cardiomyopathy": ("cat", 0.004, 0.10, False, "lethargy"),
    "obesity":             ("both", 0.04, 0.05, False, "none"),
}

# breed relative risks (synthetic); default 1.0
BREED_RR = {
    "Labrador Retriever": {"obesity": 1.8, "osteoarthritis": 1.4, "cruciate_injury": 1.5, "otitis_externa": 1.3},
    "Golden Retriever": {"mass_neoplasia": 2.2, "allergic_dermatitis": 1.4, "otitis_externa": 1.3},
    "German Shepherd": {"osteoarthritis": 1.9, "gastroenteritis": 1.4, "allergic_dermatitis": 1.3},
    "French Bulldog": {"allergic_dermatitis": 2.2, "otitis_externa": 1.6, "ivdd": 2.5},
    "Bulldog": {"allergic_dermatitis": 2.0, "otitis_externa": 1.5, "cruciate_injury": 1.4},
    "Poodle": {"dental_disease": 1.6},
    "Goldendoodle": {"otitis_externa": 1.7, "allergic_dermatitis": 1.3},
    "Labradoodle": {"otitis_externa": 1.6},
    "Beagle": {"obesity": 1.5, "ivdd": 1.5},
    "Dachshund": {"ivdd": 6.0, "dental_disease": 1.4, "obesity": 1.3},
    "Rottweiler": {"cruciate_injury": 2.2, "mass_neoplasia": 1.7, "osteoarthritis": 1.5},
    "Boxer": {"mass_neoplasia": 2.0},
    "Yorkshire Terrier": {"dental_disease": 2.0},
    "Shih Tzu": {"dental_disease": 1.7, "otitis_externa": 1.3},
    "Cavalier King Charles Spaniel": {"mitral_valve_disease": 8.0},
    "Siberian Husky": {},
    "Australian Shepherd": {},
    "Border Collie": {},
    "Pit Bull Terrier": {"allergic_dermatitis": 1.6, "cruciate_injury": 1.5},
    "Chihuahua": {"dental_disease": 2.0, "mitral_valve_disease": 2.0},
    "Maine Coon": {"hypertrophic_cardiomyopathy": 3.0, "obesity": 1.2},
    "Persian": {"chronic_kidney_disease": 1.8, "dental_disease": 1.3},
    "Siamese": {"dental_disease": 1.3},
    "Ragdoll": {"hypertrophic_cardiomyopathy": 2.0},
    "Domestic Shorthair": {"obesity": 1.2},
}

# --- Segments (latent ground truth) ---
# name: (household share, daycare days/wk, boarding trips/yr, groom propensity, wellness adherence,
#        wellness-plan enroll prob, base monthly lapse, uplift effect of reminder on lapse prob)
SEGMENTS = {
    "full_service_urban":  (0.16, 3.0, 1.5, 0.8, 0.95, 0.55, 0.020, -0.000),
    "vet_only_traditional": (0.30, 0.0, 0.1, 0.1, 0.90, 0.30, 0.012, -0.002),
    "boarding_travelers":  (0.14, 0.3, 4.0, 0.4, 0.80, 0.30, 0.030, -0.015),
    "grooming_focused":    (0.14, 0.2, 0.5, 1.0, 0.85, 0.35, 0.025, -0.010),
    "low_engagement":      (0.26, 0.0, 0.2, 0.1, 0.35, 0.10, 0.060, -0.025),
}
# uplift: negative = reminder REDUCES monthly lapse prob (persuadable)

# --- Names ---
FIRST_NAMES = """James Mary Robert Patricia John Jennifer Michael Linda David Elizabeth William Barbara Richard Susan Joseph Jessica
Thomas Sarah Christopher Karen Charles Lisa Daniel Nancy Matthew Betty Anthony Sandra Mark Margaret Donald Ashley Steven Kimberly
Andrew Emily Paul Donna Joshua Michelle Kenneth Carol Kevin Amanda Brian Melissa George Deborah Timothy Stephanie Ronald Rebecca
Jason Sharon Edward Laura Jeffrey Cynthia Ryan Dorothy Jacob Amy Gary Kathleen Nicholas Angela Eric Shirley Jonathan Brenda
Stephen Emma Larry Anna Justin Pamela Scott Nicole Brandon Samantha Benjamin Katherine Samuel Christine Gregory Helen Alexander
Debra Patrick Rachel Frank Carolyn Raymond Janet Jack Maria Dennis Catherine Jerry Heather Tyler Diane Aaron Olivia Jose Julie
Adam Joyce Nathan Victoria Henry Ruth Zachary Virginia Douglas Lauren Peter Kelly Kyle Christina Noah Joan Ethan Evelyn Jeremy
Judith Walter Andrea Christian Hannah Keith Megan Roger Cheryl Terry Jacqueline Austin Martha Sean Madison Gerald Teresa Carl
Gloria Harold Sara Dylan Janice Arthur Ann Lawrence Kathryn Jordan Abigail Jesse Sophia Bryan Frances Billy Jean Bruce Alice
Gabriel Judy Joe Isabella Logan Julia Alan Grace Juan Amber Albert Denise Willie Danielle Elijah Marilyn Wayne Beverly Randy
Charlotte Vincent Natalie Mason Theresa Roy Diana Ralph Brittany Bobby Doris Russell Kayla Bradley Alexis Philip Lori Eugene
Priya Wei Mohammed Aisha Carlos Sofia Hiroshi Mei Luis Fatima Diego Ananya Chen Elena Omar Yuki Mateo Leila Arjun Ines""".split()

LAST_NAMES = """Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Gonzalez Wilson Anderson
Thomas Taylor Moore Jackson Martin Lee Perez Thompson White Harris Sanchez Clark Ramirez Lewis Robinson Walker Young Allen King
Wright Scott Torres Nguyen Hill Flores Green Adams Nelson Baker Hall Rivera Campbell Mitchell Carter Roberts Gomez Phillips Evans
Turner Diaz Parker Cruz Edwards Collins Reyes Stewart Morris Morales Murphy Cook Rogers Gutierrez Ortiz Morgan Cooper Peterson
Bailey Reed Kelly Howard Ramos Kim Cox Ward Richardson Watson Brooks Chavez Wood James Bennett Gray Mendoza Ruiz Hughes Price
Alvarez Castillo Sanders Patel Myers Long Ross Foster Jimenez Powell Jenkins Perry Russell Sullivan Bell Coleman Butler Henderson
Barnes Gonzales Fisher Vasquez Simmons Romero Jordan Patterson Alexander Hamilton Graham Reynolds Griffin Wallace Moreno West
Cole Hayes Bryant Herrera Gibson Ellis Tran Medina Aguilar Stevens Murray Ford Castro Marshall Owens Harrison Fernandez McDonald
Woods Washington Kennedy Wells Vargas Henry Chen Freeman Webb Tucker Guzman Burns Crawford Olson Simpson Porter Hunter Gordon
Mendez Silva Shaw Snyder Mason Dixon Munoz Hunt Hicks Holmes Palmer Wagner Black Robertson Boyd Rose Stone Salazar Fox Warren
Mills Meyer Rice Schmidt Garza Daniels Ferguson Nichols Stephens Soto Weaver Ryan Gardner Payne Grant Dunn Kelley Spencer Hawkins
Lavelle OBrien McCarthy Kowalski Schneider Novak Larsen Lindqvist Johansson Haugen Nakamura Singh Shah Rao Okafor Mensah""".split()

NICKNAMES = {
    "Robert": ["Bob", "Rob", "Bobby"], "William": ["Bill", "Will", "Billy"], "Richard": ["Rick", "Dick", "Rich"],
    "James": ["Jim", "Jimmy", "Jamie"], "John": ["Jack", "Johnny"], "Michael": ["Mike", "Mikey"],
    "Elizabeth": ["Liz", "Beth", "Betsy", "Lizzie"], "Jennifer": ["Jen", "Jenny"], "Katherine": ["Kate", "Katie", "Kathy"],
    "Christopher": ["Chris", "Topher"], "Christine": ["Chris", "Chrissy"], "Daniel": ["Dan", "Danny"], "Matthew": ["Matt"],
    "Joseph": ["Joe", "Joey"], "Thomas": ["Tom", "Tommy"], "Anthony": ["Tony"], "Patricia": ["Pat", "Patty", "Trish"],
    "Margaret": ["Maggie", "Peggy", "Meg"], "Stephanie": ["Steph"], "Rebecca": ["Becky", "Becca"], "Samantha": ["Sam"],
    "Samuel": ["Sam"], "Alexander": ["Alex"], "Nicholas": ["Nick"], "Benjamin": ["Ben"], "Jonathan": ["Jon"],
    "Kimberly": ["Kim"], "Deborah": ["Deb", "Debbie"], "Susan": ["Sue", "Suzy"], "Andrew": ["Andy", "Drew"],
    "Steven": ["Steve"], "Stephen": ["Steve"], "Timothy": ["Tim"], "Gregory": ["Greg"], "Victoria": ["Vicky", "Tori"],
    "Abigail": ["Abby"], "Jacqueline": ["Jackie"], "Edward": ["Ed", "Eddie", "Ted"], "Kenneth": ["Ken", "Kenny"],
    "Donald": ["Don"], "Ronald": ["Ron"], "Lawrence": ["Larry"], "Raymond": ["Ray"], "Gerald": ["Jerry"],
}

PET_NAMES = """Bella Max Luna Charlie Lucy Cooper Daisy Milo Bailey Buddy Sadie Rocky Molly Bear Lola Duke Stella Tucker Zoe Jack
Penny Oliver Maggie Leo Chloe Teddy Sophie Winston Ruby Bentley Rosie Murphy Gracie Zeus Lily Louie Coco Jax Nala Toby Roxy
Bruno Ellie Gus Piper Ollie Willow Finn Riley Moose Hazel Henry Abby Diesel Dixie Koda Harley Ace Mia Loki Pepper Rex Ginger
Simba Olive Thor Honey Benny Millie Oscar Marley Sam Lady Apollo Kona Rufus Annie Hank Josie Ziggy Callie Tank Remi Archie
Biscuit Nova Rocco Maple Jasper Peanut Otis Poppy Kobe Sasha Beau Athena Gizmo Kiki Shadow Misty Tigger Smokey Kitty Oreo
Felix Mittens Salem Cleo Boots Whiskers Ginger Pumpkin Simba Luna Midnight Socks Patches Pickles Waffles Mochi Biscuit""".split()

PET_NAME_VARIANTS = {
    "Max": ["Maxie", "Maxwell", "MAX"], "Charlie": ["Charles", "Chuck"], "Bella": ["Bell", "Bellaboo"],
    "Cooper": ["Coop"], "Buddy": ["Bud"], "Oliver": ["Ollie"], "Winston": ["Winnie"], "Teddy": ["Ted", "Teddy Bear"],
    "Sophie": ["Sophia"], "Lucy": ["Lucille", "Lu"], "Gracie": ["Grace"], "Rosie": ["Rose"], "Benny": ["Ben"],
    "Archie": ["Arch"], "Henry": ["Hank"], "Abby": ["Abigail"], "Millie": ["Mildred"], "Louie": ["Louis", "Lou"],
}

# --- Diagnosis code systems per vet PIMS ---
# alpha: alphanumeric codes; beta: numeric codes; gamma: free text only
DX_ALPHA = {
    "allergic_dermatitis": ("DERM-ALG", "Allergic dermatitis"), "otitis_externa": ("EAR-OTE", "Otitis externa"),
    "gastroenteritis": ("GI-ACU", "Acute gastroenteritis"), "dental_disease": ("DEN-PD", "Periodontal disease"),
    "osteoarthritis": ("MSK-OA", "Osteoarthritis"), "cruciate_injury": ("MSK-CCL", "Cranial cruciate ligament rupture"),
    "ivdd": ("NEU-IVD", "Intervertebral disc disease"), "mass_neoplasia": ("ONC-MAS", "Mass, cutaneous/subcutaneous"),
    "mitral_valve_disease": ("CAR-MVD", "Myxomatous mitral valve disease"),
    "chronic_kidney_disease": ("REN-CKD", "Chronic kidney disease"),
    "hypertrophic_cardiomyopathy": ("CAR-HCM", "Hypertrophic cardiomyopathy"), "obesity": ("NUT-OBS", "Obesity"),
    "wellness": ("WEL-EXM", "Annual wellness exam"),
}
DX_BETA = {
    "allergic_dermatitis": (1104, "Atopic dermatitis"), "otitis_externa": (1210, "Ear infection"),
    "gastroenteritis": (1302, "Vomiting/diarrhea"), "dental_disease": (1401, "Dental disease grade 2-3"),
    "osteoarthritis": (1503, "Degenerative joint disease"), "cruciate_injury": (1507, "CCL tear"),
    "ivdd": (1602, "IVDD"), "mass_neoplasia": (1701, "Lump/bump - aspirate"),
    "mitral_valve_disease": (1801, "Heart murmur - MVD"), "chronic_kidney_disease": (1901, "CKD stage 2"),
    "hypertrophic_cardiomyopathy": (1805, "HCM"), "obesity": (2001, "Overweight/obese"),
    "wellness": (100, "Wellness"),
}
DX_GAMMA = {
    "allergic_dermatitis": ["itchy skin - allergies", "allergic derm", "atopy", "skin allergy flare"],
    "otitis_externa": ["ear infection", "otitis", "OE - yeast", "ears red/smelly"],
    "gastroenteritis": ["V/D", "vomiting and diarrhea", "GI upset", "gastro"],
    "dental_disease": ["dental tartar", "perio dz", "needs dental", "dental disease"],
    "osteoarthritis": ["arthritis", "DJD", "stiff hips - OA", "OA"],
    "cruciate_injury": ["ACL tear", "CCL rupture", "knee injury - cruciate"],
    "ivdd": ["back pain - IVDD", "disc disease", "IVDD"],
    "mass_neoplasia": ["lump", "mass - FNA", "skin mass", "lipoma vs other"],
    "mitral_valve_disease": ["murmur", "MVD", "heart murmur gr 3"],
    "chronic_kidney_disease": ["kidney disease", "CKD", "renal insufficiency"],
    "hypertrophic_cardiomyopathy": ["HCM", "cardiomyopathy", "heart dz"],
    "obesity": ["overweight", "obese", "weight mgmt"],
    "wellness": ["annual exam", "wellness", "vaccines + exam", "yearly"],
}

# Free-text staff notes by signal type (prodrome) and generic notes (noise)
SIGNAL_NOTES = {
    "skin": ["scratching a lot today", "red skin on belly", "licking paws constantly", "hot spot noticed"],
    "ear": ["shaking head", "ear odor noticed", "scratching ears", "ear looks red"],
    "gi": ["not eating well", "soft stool in yard", "vomited after lunch", "skipped meal"],
    "dental": ["bad breath", "dropping food", "chewing on one side"],
    "mobility": ["limping after play", "slow on stairs", "reluctant to jump", "stiff getting up"],
    "lump": ["found a lump during bath", "bump on side", "new lump noted"],
    "lethargy": ["lethargic today", "low energy", "napping more than usual", "breathing heavy at rest"],
    "none": ["happy pup", "great day"],
}
GENERIC_NOTES = ["great day", "played well with others", "happy pup", "very social", "needs nail trim",
                 "a little shy today", "loved the pool", "good boy/girl", "", "", "", "", "", "", ""]

VACCINES = {"dog": ["Rabies", "DHPP", "Bordetella", "Leptospirosis"], "cat": ["Rabies", "FVRCP", "FeLV"]}
