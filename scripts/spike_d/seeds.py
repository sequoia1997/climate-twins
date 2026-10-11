"""Curated seed lists for SPIKE D (names only; all numbers come from public APIs at run time).

Region codes use GBIF continent names: AFRICA ASIA EUROPE NORTH_AMERICA SOUTH_AMERICA OCEANIA.
For crops the region is the centre of origin / domestication (a manual, documented choice).
For trees and fish it is the native-range continent (manual) so quotas are not skewed by
where recorders live. Insects and arachnids use the GBIF majority continent unless set.
"""
AF, AS, EU, NA, SA, OC = "AFRICA", "ASIA", "EUROPE", "NORTH_AMERICA", "SOUTH_AMERICA", "OCEANIA"

# (scientific name, region, note)
CROPS = [
 ("Triticum aestivum",AS,"cereal"),("Oryza sativa",AS,"cereal"),("Zea mays",NA,"cereal"),
 ("Hordeum vulgare",AS,"cereal"),("Sorghum bicolor",AF,"cereal"),("Pennisetum glaucum",AF,"cereal"),
 ("Eleusine coracana",AF,"cereal"),("Avena sativa",EU,"cereal"),("Secale cereale",EU,"cereal"),
 ("Panicum miliaceum",AS,"cereal"),("Setaria italica",AS,"cereal"),("Fagopyrum esculentum",AS,"pseudocereal"),
 ("Chenopodium quinoa",SA,"pseudocereal"),("Eragrostis tef",AF,"cereal"),("Oryza glaberrima",AF,"cereal"),
 ("Triticum durum",AS,"cereal"),
 ("Solanum tuberosum",SA,"root/tuber"),("Manihot esculenta",SA,"root/tuber"),("Ipomoea batatas",SA,"root/tuber"),
 ("Dioscorea alata",AS,"root/tuber"),("Colocasia esculenta",AS,"root/tuber"),("Ensete ventricosum",AF,"root/tuber"),
 ("Beta vulgaris",EU,"root/sugar"),("Daucus carota",EU,"vegetable"),("Raphanus sativus",AS,"vegetable"),
 ("Glycine max",AS,"legume"),("Phaseolus vulgaris",NA,"legume"),("Vigna unguiculata",AF,"legume"),
 ("Cajanus cajan",AS,"legume"),("Cicer arietinum",AS,"legume"),("Lens culinaris",AS,"legume"),
 ("Pisum sativum",EU,"legume"),("Vicia faba",AS,"legume"),("Arachis hypogaea",SA,"legume"),
 ("Medicago sativa",AS,"forage legume"),("Trifolium repens",EU,"forage/pasture"),
 ("Brassica oleracea",EU,"vegetable"),("Brassica napus",EU,"oilseed"),("Brassica rapa",AS,"vegetable"),
 ("Helianthus annuus",NA,"oilseed"),("Gossypium hirsutum",NA,"fibre"),("Linum usitatissimum",AS,"fibre/oilseed"),
 ("Sesamum indicum",AF,"oilseed"),("Cannabis sativa",AS,"fibre/other"),("Corchorus olitorius",AS,"fibre/vegetable"),
 ("Agave sisalana",NA,"fibre"),("Hevea brasiliensis",SA,"rubber"),("Nicotiana tabacum",SA,"other"),
 ("Saccharum officinarum",OC,"sugar"),("Elaeis guineensis",AF,"oil palm"),("Cocos nucifera",OC,"palm"),
 ("Coffea arabica",AF,"beverage"),("Coffea canephora",AF,"beverage"),("Theobroma cacao",SA,"beverage"),
 ("Camellia sinensis",AS,"beverage"),("Humulus lupulus",EU,"beverage"),("Agave tequilana",NA,"beverage"),
 ("Vitis vinifera",EU,"fruit/wine"),("Malus domestica",AS,"fruit"),("Pyrus communis",EU,"fruit"),
 ("Prunus persica",AS,"fruit"),("Prunus avium",EU,"fruit"),("Prunus dulcis",AS,"nut"),
 ("Citrus sinensis",AS,"fruit"),("Citrus limon",AS,"fruit"),("Citrus reticulata",AS,"fruit"),
 ("Mangifera indica",AS,"fruit"),("Persea americana",NA,"fruit"),("Ananas comosus",SA,"fruit"),
 ("Carica papaya",NA,"fruit"),("Musa acuminata",AS,"fruit"),("Phoenix dactylifera",AS,"fruit"),
 ("Ficus carica",AS,"fruit"),("Punica granatum",AS,"fruit"),("Actinidia deliciosa",AS,"fruit"),
 ("Artocarpus altilis",OC,"fruit/starch"),("Macadamia integrifolia",OC,"nut"),
 ("Rubus idaeus",EU,"fruit"),("Vaccinium corymbosum",NA,"fruit"),("Ribes nigrum",EU,"fruit"),
 ("Cucumis sativus",AS,"vegetable"),("Cucumis melo",AF,"fruit"),("Citrullus lanatus",AF,"fruit"),
 ("Cucurbita pepo",NA,"vegetable"),("Solanum lycopersicum",SA,"vegetable"),("Solanum melongena",AS,"vegetable"),
 ("Capsicum annuum",NA,"vegetable/spice"),("Allium cepa",AS,"vegetable"),("Allium sativum",AS,"vegetable"),
 ("Lactuca sativa",EU,"vegetable"),("Spinacia oleracea",AS,"vegetable"),
 ("Piper nigrum",AS,"spice"),("Zingiber officinale",AS,"spice"),("Curcuma longa",AS,"spice"),
 ("Vanilla planifolia",NA,"spice"),("Cinnamomum verum",AS,"spice"),("Hibiscus sabdariffa",AF,"beverage/fibre"),
 ("Cyamopsis tetragonoloba",AS,"gum/forage"),
 # horticulture / ornamentals / herbs (cultivated, often escaped)
 ("Rosa chinensis",AS,"ornamental"),("Lavandula angustifolia",EU,"ornamental/herb"),
 ("Rosmarinus officinalis",EU,"herb"),("Ocimum basilicum",AS,"herb"),("Tulipa gesneriana",AS,"ornamental"),
 ("Hydrangea macrophylla",AS,"ornamental"),("Camellia japonica",AS,"ornamental"),
 ("Pelargonium zonale",AF,"ornamental"),("Bougainvillea glabra",SA,"ornamental"),
 ("Hibiscus rosa-sinensis",AS,"ornamental"),("Dahlia pinnata",NA,"ornamental"),
 ("Zantedeschia aethiopica",AF,"ornamental"),("Lantana camara",SA,"ornamental, invasive in many regions"),
]

# (scientific name, native-range region, cultivated/forestry note or "")
TREES = [
 ("Quercus alba",NA,""),("Quercus rubra",NA,""),("Quercus virginiana",NA,""),("Acer saccharum",NA,""),
 ("Acer rubrum",NA,""),("Pinus strobus",NA,""),("Pinus ponderosa",NA,""),("Pinus taeda",NA,"forestry"),
 ("Pseudotsuga menziesii",NA,"forestry"),("Sequoia sempervirens",NA,""),("Populus tremuloides",NA,""),
 ("Betula papyrifera",NA,""),("Liriodendron tulipifera",NA,""),("Platanus occidentalis",NA,""),
 ("Juglans nigra",NA,""),("Carya illinoinensis",NA,"nut crop"),("Taxodium distichum",NA,""),
 ("Thuja plicata",NA,""),("Picea sitchensis",NA,""),("Tsuga canadensis",NA,""),("Prosopis glandulosa",NA,""),
 ("Quercus robur",EU,""),("Fagus sylvatica",EU,""),("Betula pendula",EU,""),("Pinus sylvestris",EU,""),
 ("Picea abies",EU,"forestry"),("Fraxinus excelsior",EU,""),("Tilia cordata",EU,""),("Carpinus betulus",EU,""),
 ("Acer pseudoplatanus",EU,""),("Ulmus glabra",EU,""),("Salix alba",EU,""),("Alnus glutinosa",EU,""),
 ("Sorbus aucuparia",EU,""),("Taxus baccata",EU,""),("Abies alba",EU,""),("Larix decidua",EU,""),
 ("Cedrus libani",AS,"native Levant, ornamental widely"),("Olea europaea",EU,"cultivated crop tree"),
 ("Castanea sativa",EU,"cultivated"),("Quercus ilex",EU,""),("Quercus suber",EU,"cork crop"),
 ("Pinus pinea",EU,"cultivated"),("Pinus halepensis",EU,""),("Cupressus sempervirens",EU,"ornamental"),
 ("Ceratonia siliqua",EU,"cultivated"),("Laurus nobilis",EU,""),("Aesculus hippocastanum",EU,"ornamental"),
 ("Juniperus communis",EU,""),("Populus nigra",EU,""),
 ("Tectona grandis",AS,"plantation forestry, planted widely"),("Cryptomeria japonica",AS,"forestry"),
 ("Cinnamomum camphora",AS,"ornamental, invasive in places"),("Morus alba",AS,"cultivated"),
 ("Dalbergia sissoo",AS,"planted"),("Shorea robusta",AS,""),("Ficus religiosa",AS,""),("Ficus benghalensis",AS,""),
 ("Azadirachta indica",AS,"planted widely"),("Pinus densiflora",AS,""),("Pinus koraiensis",AS,""),
 ("Larix gmelinii",AS,""),("Betula platyphylla",AS,""),("Quercus mongolica",AS,""),("Prunus serrulata",AS,"ornamental"),
 ("Paulownia tomentosa",AS,"ornamental, invasive in places"),("Ailanthus altissima",AS,"invasive in many regions"),
 ("Cedrus deodara",AS,""),("Pinus roxburghii",AS,""),("Rhododendron arboreum",AS,""),("Phyllanthus emblica",AS,""),
 ("Toona sinensis",AS,""),("Albizia julibrissin",AS,"ornamental, invasive in places"),("Pterocarpus indicus",AS,""),
 ("Adansonia digitata",AF,""),("Vachellia tortilis",AF,""),("Vachellia xanthophloea",AF,""),
 ("Senegalia senegal",AF,""),("Faidherbia albida",AF,""),("Sclerocarya birrea",AF,""),
 ("Colophospermum mopane",AF,""),("Brachystegia spiciformis",AF,""),("Terminalia sericea",AF,""),
 ("Ceiba pentandra",AF,""),("Milicia excelsa",AF,""),("Ficus sycomorus",AF,""),("Balanites aegyptiaca",AF,""),
 ("Parkia biglobosa",AF,""),("Tamarindus indica",AF,"planted pantropically"),("Spathodea campanulata",AF,"ornamental, invasive in places"),
 ("Vachellia nilotica",AF,"planted/invasive in places"),("Euphorbia ingens",AF,""),
 ("Swietenia macrophylla",SA,"plantation forestry"),("Cecropia peltata",SA,""),("Handroanthus impetiginosus",SA,""),
 ("Jacaranda mimosifolia",SA,"ornamental worldwide"),("Schinus molle",SA,"ornamental/invasive in places"),
 ("Nothofagus pumilio",SA,""),("Nothofagus antarctica",SA,""),("Prosopis alba",SA,""),("Ceiba speciosa",SA,"ornamental"),
 ("Erythrina crista-galli",SA,""),("Inga edulis",SA,""),("Hymenaea courbaril",SA,""),("Euterpe oleracea",SA,""),
 ("Tabebuia rosea",SA,""),("Ochroma pyramidale",SA,""),("Guazuma ulmifolia",SA,""),("Quillaja saponaria",SA,""),
 ("Eucalyptus camaldulensis",OC,"forestry, planted worldwide"),("Eucalyptus globulus",OC,"forestry, planted worldwide"),
 ("Eucalyptus regnans",OC,""),("Eucalyptus grandis",OC,"forestry"),("Eucalyptus marginata",OC,""),
 ("Corymbia citriodora",OC,"planted"),("Acacia dealbata",OC,"invasive in many regions"),
 ("Acacia melanoxylon",OC,"invasive in places"),("Acacia pycnantha",OC,""),("Casuarina equisetifolia",OC,"planted"),
 ("Melaleuca quinquenervia",OC,"invasive in Florida"),("Araucaria heterophylla",OC,"ornamental"),
 ("Agathis australis",OC,""),("Podocarpus totara",OC,""),("Metrosideros excelsa",OC,""),
 ("Banksia integrifolia",OC,""),("Grevillea robusta",OC,"planted"),("Pandanus tectorius",OC,""),
 ("Leptospermum scoparium",OC,""),("Eucalyptus obliqua",OC,""),("Eucalyptus saligna",OC,"forestry"),
 ("Pinus radiata",NA,"native California, the world's main plantation pine in SH"),
]

FISH = [  # freshwater (some anadromous / widely stocked: noted)
 ("Oncorhynchus mykiss",NA,"stocked worldwide"),("Salmo trutta",EU,"stocked worldwide, invasive in places"),
 ("Salvelinus fontinalis",NA,"stocked"),("Salvelinus namaycush",NA,""),("Esox lucius",EU,""),
 ("Esox masquinongy",NA,""),("Micropterus salmoides",NA,"stocked/invasive worldwide"),
 ("Micropterus dolomieu",NA,"stocked"),("Sander vitreus",NA,""),("Sander lucioperca",EU,"stocked"),
 ("Perca fluviatilis",EU,""),("Perca flavescens",NA,""),("Cyprinus carpio",AS,"domesticated/invasive worldwide"),
 ("Carassius auratus",AS,"domesticated/invasive"),("Lepomis macrochirus",NA,"stocked"),
 ("Ictalurus punctatus",NA,"aquaculture"),("Thymallus thymallus",EU,""),("Rutilus rutilus",EU,""),
 ("Tinca tinca",EU,""),("Lota lota",EU,""),("Gambusia affinis",NA,"invasive worldwide"),
 ("Oreochromis niloticus",AF,"aquaculture worldwide"),("Clarias gariepinus",AF,"aquaculture"),
 ("Lates niloticus",AF,"invasive Lake Victoria"),("Hoplias malabaricus",SA,""),("Cichla ocellaris",SA,"introduced"),
 ("Hypophthalmichthys molitrix",AS,"invasive in NA/EU"),("Ctenopharyngodon idella",AS,"stocked worldwide"),
 ("Barbus barbus",EU,""),("Labeo rohita",AS,"aquaculture"),("Catla catla",AS,"aquaculture"),
 ("Channa argus",AS,"invasive in NA"),("Astyanax mexicanus",NA,""),("Macquaria ambigua",OC,""),
 ("Leuciscus leuciscus",EU,""),("Abramis brama",EU,""),("Coregonus lavaretus",EU,""),
 ("Pylodictis olivaris",NA,""),("Oncorhynchus clarkii",NA,""),("Salmo salar",EU,"anadromous; mixed freshwater/marine life history"),
]

# insects and arachnids: must-include named taxa (region None = GBIF majority continent)
INSECTS = [
 ("Danaus plexippus",None,"monarch; IUCN lists the migratory form as threatened, kept because requested"),
 ("Apis mellifera",None,"managed honeybee, introduced worldwide"),("Apis cerana",None,""),("Apis dorsata",None,""),
 ("Bombus terrestris",None,""),("Bombus lapidarius",None,""),("Bombus pascuorum",None,""),("Bombus lucorum",None,""),
 ("Bombus impatiens",None,""),("Bombus bimaculatus",None,""),("Bombus pensylvanicus",None,""),
 ("Aedes aegypti",None,"disease vector"),("Aedes albopictus",None,"disease vector, invasive"),
 ("Anopheles gambiae",None,"disease vector"),("Anopheles stephensi",None,"disease vector"),
 ("Culex pipiens",None,"disease vector"),("Culex quinquefasciatus",None,"disease vector"),
 ("Ixodes scapularis",None,"tick, Lyme vector"),("Ixodes ricinus",None,"tick, Lyme vector"),
 ("Amblyomma americanum",None,"tick"),("Dermacentor variabilis",None,"tick"),
 ("Rhipicephalus sanguineus",None,"tick"),("Hyalomma marginatum",None,"tick"),
 ("Vanessa cardui",None,"migratory butterfly"),("Pieris rapae",None,""),("Papilio machaon",None,""),
 ("Coccinella septempunctata",None,""),("Harmonia axyridis",None,"invasive"),
 ("Locusta migratoria",None,"pest"),("Schistocerca gregaria",None,"pest"),
 ("Spodoptera frugiperda",None,"crop pest, invasive"),("Helicoverpa armigera",None,"crop pest"),
 ("Lymantria dispar",None,"forest pest"),("Leptinotarsa decemlineata",None,"crop pest"),
 ("Bombyx mori",None,"domesticated silkworm"),("Phyllocnistis citrella",None,""),
 ("Tetranychus urticae",None,"crop pest, mite"),("Aphis gossypii",None,"crop pest"),
 ("Diabrotica virgifera",None,"crop pest"),("Halyomorpha halys",None,"crop pest, invasive"),
 ("Xylocopa violacea",None,""),("Vespula vulgaris",None,""),("Vespa crabro",None,""),
 ("Anopheles funestus",None,"disease vector"),("Phlebotomus papatasi",None,"sandfly vector"),
]

# Species that must never enter (domesticated animals, humans, commensals). Not model targets.
DOMESTIC_OR_ODD = {
 "Homo sapiens","Felis catus","Canis familiaris","Canis lupus familiaris","Bos taurus","Bos indicus","Ovis aries",
 "Capra hircus","Equus caballus","Equus asinus","Sus domesticus","Gallus gallus","Mus musculus","Rattus rattus",
 "Rattus norvegicus","Columba livia","Camelus dromedarius","Anser anser domesticus","Meleagris gallopavo domesticus",
 "Oryctolagus cuniculus","Cavia porcellus","Bubalus bubalis","Lama glama","Anas platyrhynchos domesticus",
 "Streptopelia roseogrisea","Melopsittacus undulatus","Taeniopygia guttata","Trachemys scripta",
}
INVASIVE_CURATED = {
 "Sturnus vulgaris","Passer domesticus","Acridotheres tristis","Rattus rattus","Lantana camara","Eichhornia crassipes",
 "Rhinella marina","Trachemys scripta","Lithobates catesbeianus","Anolis sagrei","Pycnonotus cafer","Eleutherodactylus coqui",
 "Sus scrofa","Oryctolagus cuniculus","Vulpes vulpes","Cervus elaphus","Ailanthus altissima","Acacia dealbata",
}
# Seabird / marine mammal / sea-turtle families dropped as marine-associated
MARINE_FAMILIES = {
 "Diomedeidae","Procellariidae","Hydrobatidae","Oceanitidae","Spheniscidae","Sulidae","Fregatidae","Phaethontidae",
 "Stercorariidae","Alcidae","Laridae","Sternidae","Pelecanoididae","Phocidae","Otariidae","Odobenidae","Delphinidae",
 "Balaenopteridae","Physeteridae","Phocoenidae","Trichechidae","Dugongidae","Balaenidae","Cheloniidae","Dermochelyidae",
 "Haematopodidae","Hydrophiidae",
}
# Genera treated as trees when screening iNaturalist plant pools (heuristic; includes tree-like shrubs)
TREE_GENERA = set("""Quercus Acer Pinus Picea Abies Larix Pseudotsuga Tsuga Cedrus Cupressus Juniperus Thuja Taxus Sequoia Sequoiadendron
Taxodium Fagus Betula Alnus Carpinus Corylus Castanea Castanopsis Lithocarpus Ulmus Zelkova Celtis Fraxinus Tilia Populus Salix Platanus
Liquidambar Liriodendron Magnolia Juglans Carya Eucalyptus Corymbia Acacia Vachellia Senegalia Faidherbia Prosopis Albizia Samanea Inga Cassia
Senna Delonix Tamarindus Ceiba Bombax Adansonia Ficus Morus Tectona Swietenia Cedrela Khaya Terminalia Combretum Syzygium Melaleuca
Casuarina Allocasuarina Agathis Araucaria Podocarpus Nothofagus Metrosideros Banksia Grevillea Hakea Cecropia Jacaranda Handroanthus
Tabebuia Spathodea Erythrina Prunus Pyrus Malus Sorbus Crataegus Aesculus Olea Ceratonia Laurus Cinnamomum Persea Ocotea Nectandra
Schinus Pistacia Rhus Ailanthus Azadirachta Melia Toona Shorea Dipterocarpus Hopea Dalbergia Pterocarpus Millettia Brachystegia
Colophospermum Sclerocarya Balanites Parkia Milicia Albizzia Paulownia Catalpa Ginkgo Cryptomeria Metasequoia Sassafras Nyssa
Cornus Ilex Carpinus Ostrya Robinia Gleditsia Gymnocladus Cercis Koelreuteria Sapindus Ochroma Guazuma Quillaja Cocos Phoenix
Washingtonia Roystonea Sabal Euterpe Pandanus Dracaena Yucca Cordyline Leptospermum Kunzea Brachychiton Flindersia Elaeocarpus
Cinchona Hevea Hymenaea Dipteryx Bertholletia Lecythis Handroanthus Zanthoxylum Fagara Bursera Gliricidia Leucaena Pithecellobium
Sequoia Calocedrus Chamaecyparis Cunninghamia Pseudolarix Keteleeria Platycladus Tetraclinis Arbutus Rhododendron Ziziphus
Anacardium Mangifera Bauhinia Butea Cassia Peltophorum Pongamia Millettia Terminalia Lagerstroemia Trema Macaranga Ochroma
Prunus Amelanchier Sambucus Fraxinus Liquidambar Eucommia Idesia Sapium Triadica Mallotus Bischofia Dillenia""".split())

# must survive the cut to the 350 shortlist (named in the brief)
CORE = {"Danaus plexippus","Apis mellifera","Bombus terrestris","Aedes aegypti","Aedes albopictus","Ixodes scapularis","Ixodes ricinus",
        "Anopheles gambiae","Culex pipiens"}
