# -*- coding: utf-8 -*-
import json


# =========================================================================
# BARSIT — TEST RÁPIDO DE BARRANQUILLA (HABILIDAD MENTAL / INTELIGENCIA)
# =========================================================================

BARSIT_ITEMS = [
    {
        "id": 1,
        "area": "Información y Conocimientos Generales",
        "texto": "1.- El queso se fabrica de:",
        "opciones": [
            {
                "val": 1,
                "text": "Las flores"
            },
            {
                "val": 2,
                "text": "La harina"
            },
            {
                "val": 3,
                "text": "La leche"
            },
            {
                "val": 4,
                "text": "Las uvas"
            },
            {
                "val": 5,
                "text": "El azúcar"
            }
        ]
    },
    {
        "id": 2,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "2.- Lo contrario de abierto es:",
        "opciones": [
            {
                "val": 1,
                "text": "Liso"
            },
            {
                "val": 2,
                "text": "Cerrado"
            },
            {
                "val": 3,
                "text": "Delante"
            },
            {
                "val": 4,
                "text": "Claro"
            },
            {
                "val": 5,
                "text": "Despejado"
            }
        ]
    },
    {
        "id": 3,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "3.- De las siguientes palabras una pertenece a una clase diferente ¿cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Rojo"
            },
            {
                "val": 2,
                "text": "Amarillo"
            },
            {
                "val": 3,
                "text": "Morado"
            },
            {
                "val": 4,
                "text": "Bandera"
            },
            {
                "val": 5,
                "text": "Verde"
            }
        ]
    },
    {
        "id": 4,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "4.- El pájaro canta y el perro...",
        "opciones": [
            {
                "val": 1,
                "text": "Habla"
            },
            {
                "val": 2,
                "text": "Rebuzna"
            },
            {
                "val": 3,
                "text": "Cacarea"
            },
            {
                "val": 4,
                "text": "Maúlla"
            },
            {
                "val": 5,
                "text": "ladra"
            }
        ]
    },
    {
        "id": 5,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "5.- Escribe los dos números que faltan a esta serie (10 15 20 25     _____    35 40     _______  50)",
        "opciones": [
            {
                "val": 1,
                "text": "28 y 45"
            },
            {
                "val": 2,
                "text": "30 y 48"
            },
            {
                "val": 3,
                "text": "30 y 50"
            },
            {
                "val": 4,
                "text": "32 y 52"
            },
            {
                "val": 5,
                "text": "25 y 55"
            }
        ]
    },
    {
        "id": 6,
        "area": "Información y Conocimientos Generales",
        "texto": "6.- Para medir la temperatura se emplea...",
        "opciones": [
            {
                "val": 1,
                "text": "Litro"
            },
            {
                "val": 2,
                "text": "Gramo"
            },
            {
                "val": 3,
                "text": "Termómetro"
            },
            {
                "val": 4,
                "text": "Metro"
            },
            {
                "val": 5,
                "text": "Kilowatio"
            }
        ]
    },
    {
        "id": 7,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "7.- Lo contrario de dormido es",
        "opciones": [
            {
                "val": 1,
                "text": "Noche"
            },
            {
                "val": 2,
                "text": "Luz"
            },
            {
                "val": 3,
                "text": "Amanecer"
            },
            {
                "val": 4,
                "text": "Despierto"
            },
            {
                "val": 5,
                "text": "Día"
            }
        ]
    },
    {
        "id": 8,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "8.- De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Agua"
            },
            {
                "val": 2,
                "text": "Platino"
            },
            {
                "val": 3,
                "text": "Café"
            },
            {
                "val": 4,
                "text": "Té"
            },
            {
                "val": 5,
                "text": "Cerveza"
            }
        ]
    },
    {
        "id": 9,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "9.- El zapato protege al pie, y el sombrero protege a:",
        "opciones": [
            {
                "val": 1,
                "text": "La cabeza"
            },
            {
                "val": 2,
                "text": "La mano"
            },
            {
                "val": 3,
                "text": "El dedo"
            },
            {
                "val": 4,
                "text": "El brazo"
            },
            {
                "val": 5,
                "text": "La rodilla"
            }
        ]
    },
    {
        "id": 10,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "10.- Escriba los números que faltan a esta serie (6 9 12______ 18 21 24______ 30)",
        "opciones": [
            {
                "val": 1,
                "text": "14 y 26"
            },
            {
                "val": 2,
                "text": "15 y 27"
            },
            {
                "val": 3,
                "text": "16 y 28"
            },
            {
                "val": 4,
                "text": "15 y 26"
            },
            {
                "val": 5,
                "text": "14 y 28"
            }
        ]
    },
    {
        "id": 11,
        "area": "Información y Conocimientos Generales",
        "texto": "11.- El triángulo es una figura formada por",
        "opciones": [
            {
                "val": 1,
                "text": "4 lados"
            },
            {
                "val": 2,
                "text": "6 lados"
            },
            {
                "val": 3,
                "text": "65 lados"
            },
            {
                "val": 4,
                "text": "3 lados"
            },
            {
                "val": 5,
                "text": "9 lados"
            }
        ]
    },
    {
        "id": 12,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "12.- Lo contrario de negro es:",
        "opciones": [
            {
                "val": 1,
                "text": "Oscuro"
            },
            {
                "val": 2,
                "text": "Sombra"
            },
            {
                "val": 3,
                "text": "Opaco"
            },
            {
                "val": 4,
                "text": "Sucio"
            },
            {
                "val": 5,
                "text": "Blanco"
            }
        ]
    },
    {
        "id": 13,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "13.- De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Enrique"
            },
            {
                "val": 2,
                "text": "Pedro"
            },
            {
                "val": 3,
                "text": "Ana"
            },
            {
                "val": 4,
                "text": "José"
            },
            {
                "val": 5,
                "text": "Carlos"
            }
        ]
    },
    {
        "id": 14,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "14.- El naranjo es un árbol, y el perro es:",
        "opciones": [
            {
                "val": 1,
                "text": "Un objeto"
            },
            {
                "val": 2,
                "text": "Un animal"
            },
            {
                "val": 3,
                "text": "Una cosa"
            },
            {
                "val": 4,
                "text": "Un mineral"
            },
            {
                "val": 5,
                "text": "Un vegetal"
            }
        ]
    },
    {
        "id": 15,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "15.- Escriba los números que faltan a esta serie: (7 9 11 13    ____ 17   ____ 21 23)",
        "opciones": [
            {
                "val": 1,
                "text": "15 y 19"
            },
            {
                "val": 2,
                "text": "14 y 18"
            },
            {
                "val": 3,
                "text": "16 y 20"
            },
            {
                "val": 4,
                "text": "15 y 18"
            },
            {
                "val": 5,
                "text": "14 y 19"
            }
        ]
    },
    {
        "id": 16,
        "area": "Información y Conocimientos Generales",
        "texto": "16.- El gato es un:",
        "opciones": [
            {
                "val": 1,
                "text": "Mamífero"
            },
            {
                "val": 2,
                "text": "Insecto"
            },
            {
                "val": 3,
                "text": "Ave"
            },
            {
                "val": 4,
                "text": "Pez"
            },
            {
                "val": 5,
                "text": "Reptil"
            }
        ]
    },
    {
        "id": 17,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "17.- Lo contrario de triste es:",
        "opciones": [
            {
                "val": 1,
                "text": "Alegre"
            },
            {
                "val": 2,
                "text": "Preocupado"
            },
            {
                "val": 3,
                "text": "Dolorido"
            },
            {
                "val": 4,
                "text": "Desgraciado"
            },
            {
                "val": 5,
                "text": "Enfermo"
            }
        ]
    },
    {
        "id": 18,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "18.- De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Bogotá"
            },
            {
                "val": 2,
                "text": "Lima"
            },
            {
                "val": 3,
                "text": "Alpes"
            },
            {
                "val": 4,
                "text": "Caracas"
            },
            {
                "val": 5,
                "text": "Quito"
            }
        ]
    },
    {
        "id": 19,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "19.- La piel cubre al hombre, y las plumas cubren a:",
        "opciones": [
            {
                "val": 1,
                "text": "La vaca"
            },
            {
                "val": 2,
                "text": "El perro"
            },
            {
                "val": 3,
                "text": "El gato"
            },
            {
                "val": 4,
                "text": "La gallina"
            },
            {
                "val": 5,
                "text": "El caballo"
            }
        ]
    },
    {
        "id": 20,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "20.- Escriba los números que faltan a esta serie: (7      14 21      28 ______ 42       49 _______ 63 70)",
        "opciones": [
            {
                "val": 1,
                "text": "32 y 54"
            },
            {
                "val": 2,
                "text": "35 y 56"
            },
            {
                "val": 3,
                "text": "36 y 58"
            },
            {
                "val": 4,
                "text": "34 y 55"
            },
            {
                "val": 5,
                "text": "35 y 54"
            }
        ]
    },
    {
        "id": 21,
        "area": "Información y Conocimientos Generales",
        "texto": "21.- Treinta es el triple de:",
        "opciones": [
            {
                "val": 1,
                "text": "Quince"
            },
            {
                "val": 2,
                "text": "Tres"
            },
            {
                "val": 3,
                "text": "Diez"
            },
            {
                "val": 4,
                "text": "Doce"
            },
            {
                "val": 5,
                "text": "Cinco"
            }
        ]
    },
    {
        "id": 22,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "22.- Lo contrario de calor es:",
        "opciones": [
            {
                "val": 1,
                "text": "Sudor"
            },
            {
                "val": 2,
                "text": "Fatiga"
            },
            {
                "val": 3,
                "text": "Blanco"
            },
            {
                "val": 4,
                "text": "Frío"
            },
            {
                "val": 5,
                "text": "Luz"
            }
        ]
    },
    {
        "id": 23,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "23.- De estas cinco palabras, una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Cuchara"
            },
            {
                "val": 2,
                "text": "Plato"
            },
            {
                "val": 3,
                "text": "Tenedor"
            },
            {
                "val": 4,
                "text": "Cuchillo"
            },
            {
                "val": 5,
                "text": "Cucharita"
            }
        ]
    },
    {
        "id": 24,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "24.- Para coser se emplea la aguja, y para dibujar se emplea el:",
        "opciones": [
            {
                "val": 1,
                "text": "Lápiz"
            },
            {
                "val": 2,
                "text": "Bastón"
            },
            {
                "val": 3,
                "text": "Tintero"
            },
            {
                "val": 4,
                "text": "Pie"
            },
            {
                "val": 5,
                "text": "Ojo"
            }
        ]
    },
    {
        "id": 25,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "25.- Escriba los números que faltan a esta serie: (40        36 32          28 ______ 20         16    12 _____ 4)",
        "opciones": [
            {
                "val": 1,
                "text": "26 y 10"
            },
            {
                "val": 2,
                "text": "22 y 6"
            },
            {
                "val": 3,
                "text": "24 y 8"
            },
            {
                "val": 4,
                "text": "25 y 7"
            },
            {
                "val": 5,
                "text": "24 y 6"
            }
        ]
    },
    {
        "id": 26,
        "area": "Información y Conocimientos Generales",
        "texto": "26.- La cordillera de los Andes está en:",
        "opciones": [
            {
                "val": 1,
                "text": "Europa"
            },
            {
                "val": 2,
                "text": "Asia"
            },
            {
                "val": 3,
                "text": "América"
            },
            {
                "val": 4,
                "text": "Austria"
            },
            {
                "val": 5,
                "text": "África"
            }
        ]
    },
    {
        "id": 27,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "27.- Lo contrario de arriba es:",
        "opciones": [
            {
                "val": 1,
                "text": "Dentro"
            },
            {
                "val": 2,
                "text": "Abajo"
            },
            {
                "val": 3,
                "text": "Cerca"
            },
            {
                "val": 4,
                "text": "Completo"
            },
            {
                "val": 5,
                "text": "Lejos"
            }
        ]
    },
    {
        "id": 28,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "28.- De estas cinco palabras, una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "General"
            },
            {
                "val": 2,
                "text": "Teniente"
            },
            {
                "val": 3,
                "text": "Capitán"
            },
            {
                "val": 4,
                "text": "Presidente"
            },
            {
                "val": 5,
                "text": "Coronel"
            }
        ]
    },
    {
        "id": 29,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "29.- Con el cuero se fabrica el calzado, y con la tela:",
        "opciones": [
            {
                "val": 1,
                "text": "Piel"
            },
            {
                "val": 2,
                "text": "Lana"
            },
            {
                "val": 3,
                "text": "Algodón"
            },
            {
                "val": 4,
                "text": "Seda"
            },
            {
                "val": 5,
                "text": "Vestidos"
            }
        ]
    },
    {
        "id": 30,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "30.- Escriba los dos números que faltan a esta serie: (64        58 52          46 ______ 34         28   _____ 16 10 4)",
        "opciones": [
            {
                "val": 1,
                "text": "42 y 24"
            },
            {
                "val": 2,
                "text": "40 y 22"
            },
            {
                "val": 3,
                "text": "38 y 20"
            },
            {
                "val": 4,
                "text": "40 y 20"
            },
            {
                "val": 5,
                "text": "42 y 22"
            }
        ]
    },
    {
        "id": 31,
        "area": "Información y Conocimientos Generales",
        "texto": "31.- Roma es la Capital de:",
        "opciones": [
            {
                "val": 1,
                "text": "Nicaragua"
            },
            {
                "val": 2,
                "text": "España"
            },
            {
                "val": 3,
                "text": "Grecia"
            },
            {
                "val": 4,
                "text": "Italia"
            },
            {
                "val": 5,
                "text": "Paraguay"
            }
        ]
    },
    {
        "id": 32,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "32.- Lo contrario de si es:",
        "opciones": [
            {
                "val": 1,
                "text": "Antes"
            },
            {
                "val": 2,
                "text": "Afirmar"
            },
            {
                "val": 3,
                "text": "Duda"
            },
            {
                "val": 4,
                "text": "Luego"
            },
            {
                "val": 5,
                "text": "No"
            }
        ]
    },
    {
        "id": 33,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "33.- De estas cinco palabras, una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Vaso"
            },
            {
                "val": 2,
                "text": "Copa"
            },
            {
                "val": 3,
                "text": "Agua"
            },
            {
                "val": 4,
                "text": "Jarra"
            },
            {
                "val": 5,
                "text": "Taza"
            }
        ]
    },
    {
        "id": 34,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "34.- La Nariz sirve para oler, y los ojos sirven para:",
        "opciones": [
            {
                "val": 1,
                "text": "Oir"
            },
            {
                "val": 2,
                "text": "Ver"
            },
            {
                "val": 3,
                "text": "Gustar"
            },
            {
                "val": 4,
                "text": "Tocar"
            },
            {
                "val": 5,
                "text": "Andar"
            }
        ]
    },
    {
        "id": 35,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "35.- Escriba los dos números que faltan a esta serie: (5       10 20  ______ 80        160    ______ 640 1280)",
        "opciones": [
            {
                "val": 1,
                "text": "30 y 240"
            },
            {
                "val": 2,
                "text": "40 y 320"
            },
            {
                "val": 3,
                "text": "50 y 300"
            },
            {
                "val": 4,
                "text": "40 y 280"
            },
            {
                "val": 5,
                "text": "45 y 320"
            }
        ]
    },
    {
        "id": 36,
        "area": "Información y Conocimientos Generales",
        "texto": "36.- El idioma oficial de Haití es el:",
        "opciones": [
            {
                "val": 1,
                "text": "Inglés"
            },
            {
                "val": 2,
                "text": "Francés"
            },
            {
                "val": 3,
                "text": "Español"
            },
            {
                "val": 4,
                "text": "Holandés"
            },
            {
                "val": 5,
                "text": "Portugués"
            }
        ]
    },
    {
        "id": 37,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "37.- Lo contrario de despacio es :",
        "opciones": [
            {
                "val": 1,
                "text": "De prisa"
            },
            {
                "val": 2,
                "text": "Lento"
            },
            {
                "val": 3,
                "text": "Pausado"
            },
            {
                "val": 4,
                "text": "Débil"
            },
            {
                "val": 5,
                "text": "Grueso"
            }
        ]
    },
    {
        "id": 38,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "38.- De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Carpintero"
            },
            {
                "val": 2,
                "text": "Herrero"
            },
            {
                "val": 3,
                "text": "Médico"
            },
            {
                "val": 4,
                "text": "Albañil"
            },
            {
                "val": 5,
                "text": "Zapatero"
            }
        ]
    },
    {
        "id": 39,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "39.- Al lunes sigue el martes, y a enero sigue:",
        "opciones": [
            {
                "val": 1,
                "text": "Junio"
            },
            {
                "val": 2,
                "text": "Viernes"
            },
            {
                "val": 3,
                "text": "Mes"
            },
            {
                "val": 4,
                "text": "Febrero"
            },
            {
                "val": 5,
                "text": "Año"
            }
        ]
    },
    {
        "id": 40,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "40.- Escriba los dos números que faltan a esta serie: (2    4 ______ 16       22 32    _____ 128 256)",
        "opciones": [
            {
                "val": 1,
                "text": "6 y 48"
            },
            {
                "val": 2,
                "text": "8 y 64"
            },
            {
                "val": 3,
                "text": "10 y 64"
            },
            {
                "val": 4,
                "text": "8 y 56"
            },
            {
                "val": 5,
                "text": "6 y 64"
            }
        ]
    },
    {
        "id": 41,
        "area": "Información y Conocimientos Generales",
        "texto": "41.- Fernando Magallanes fue un famoso:",
        "opciones": [
            {
                "val": 1,
                "text": "Militar"
            },
            {
                "val": 2,
                "text": "Aviador"
            },
            {
                "val": 3,
                "text": "Navegante"
            },
            {
                "val": 4,
                "text": "Sabio"
            },
            {
                "val": 5,
                "text": "Sacerdote"
            }
        ]
    },
    {
        "id": 42,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "42.- Lo contrario de blando es:",
        "opciones": [
            {
                "val": 1,
                "text": "Suave"
            },
            {
                "val": 2,
                "text": "Duro"
            },
            {
                "val": 3,
                "text": "Liso"
            },
            {
                "val": 4,
                "text": "Grueso"
            },
            {
                "val": 5,
                "text": "Débil"
            }
        ]
    },
    {
        "id": 43,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "43.- De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Ver"
            },
            {
                "val": 2,
                "text": "Oir"
            },
            {
                "val": 3,
                "text": "Oler"
            },
            {
                "val": 4,
                "text": "Andar"
            },
            {
                "val": 5,
                "text": "Gustar"
            }
        ]
    },
    {
        "id": 44,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "44.- El codo articula el brazo, y la rodilla articula:",
        "opciones": [
            {
                "val": 1,
                "text": "El corazón"
            },
            {
                "val": 2,
                "text": "Los dedos"
            },
            {
                "val": 3,
                "text": "Los pulmones"
            },
            {
                "val": 4,
                "text": "El cerebro"
            },
            {
                "val": 5,
                "text": "La pierna"
            }
        ]
    },
    {
        "id": 45,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "45.- Escriba los dos números que faltan a esta serie: (5    6       8   11     15 20    _____ 33       41 _____ 60)",
        "opciones": [
            {
                "val": 1,
                "text": "25 y 48"
            },
            {
                "val": 2,
                "text": "27 y 52"
            },
            {
                "val": 3,
                "text": "26 y 50"
            },
            {
                "val": 4,
                "text": "26 y 49"
            },
            {
                "val": 5,
                "text": "24 y 50"
            }
        ]
    },
    {
        "id": 46,
        "area": "Información y Conocimientos Generales",
        "texto": "46.- Cristóbal Colón descubrió América en el:",
        "opciones": [
            {
                "val": 1,
                "text": "Siglo XIII"
            },
            {
                "val": 2,
                "text": "Siglo XVII"
            },
            {
                "val": 3,
                "text": "Siglo IV"
            },
            {
                "val": 4,
                "text": "Siglo XV"
            },
            {
                "val": 5,
                "text": "Siglo XIV"
            }
        ]
    },
    {
        "id": 47,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "47.- Lo contrario de fuera es:",
        "opciones": [
            {
                "val": 1,
                "text": "Libre"
            },
            {
                "val": 2,
                "text": "Lejos"
            },
            {
                "val": 3,
                "text": "Distinto"
            },
            {
                "val": 4,
                "text": "Malo"
            },
            {
                "val": 5,
                "text": "Dentro"
            }
        ]
    },
    {
        "id": 48,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "48.- De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Venus"
            },
            {
                "val": 2,
                "text": "Júpiter"
            },
            {
                "val": 3,
                "text": "Satélite"
            },
            {
                "val": 4,
                "text": "Urano"
            },
            {
                "val": 5,
                "text": "Neptuno"
            }
        ]
    },
    {
        "id": 49,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "49.- Octubre es anterior a Noviembre y Jueves es anterior a:",
        "opciones": [
            {
                "val": 1,
                "text": "Diciembre"
            },
            {
                "val": 2,
                "text": "Viernes"
            },
            {
                "val": 3,
                "text": "Septiembre"
            },
            {
                "val": 4,
                "text": "Miércoles"
            },
            {
                "val": 5,
                "text": "Día"
            }
        ]
    },
    {
        "id": 50,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "50.- Escriba los dos números que faltan a esta serie: (90      80 71      63 ______ 50        45    _____ 38       36 35)",
        "opciones": [
            {
                "val": 1,
                "text": "55 y 40"
            },
            {
                "val": 2,
                "text": "56 y 41"
            },
            {
                "val": 3,
                "text": "57 y 42"
            },
            {
                "val": 4,
                "text": "54 y 39"
            },
            {
                "val": 5,
                "text": "56 y 40"
            }
        ]
    },
    {
        "id": 51,
        "area": "Información y Conocimientos Generales",
        "texto": "51.- Los primeros ferrocarriles empezaron a funcionar hacia:",
        "opciones": [
            {
                "val": 1,
                "text": "1900"
            },
            {
                "val": 2,
                "text": "1800"
            },
            {
                "val": 3,
                "text": "1825"
            },
            {
                "val": 4,
                "text": "1750"
            },
            {
                "val": 5,
                "text": "1710"
            }
        ]
    },
    {
        "id": 52,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "52.- Lo contrario de empezar es:",
        "opciones": [
            {
                "val": 1,
                "text": "Iniciar"
            },
            {
                "val": 2,
                "text": "Adelantar"
            },
            {
                "val": 3,
                "text": "Obstruir"
            },
            {
                "val": 4,
                "text": "Terminar"
            },
            {
                "val": 5,
                "text": "Buscar"
            }
        ]
    },
    {
        "id": 53,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "53.- De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Feliz"
            },
            {
                "val": 2,
                "text": "Triste"
            },
            {
                "val": 3,
                "text": "Satisfecho"
            },
            {
                "val": 4,
                "text": "Alegre"
            },
            {
                "val": 5,
                "text": "Contento"
            }
        ]
    },
    {
        "id": 54,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "54.- La paz viene después de la guerra y la calma viene después de:",
        "opciones": [
            {
                "val": 1,
                "text": "La tormenta"
            },
            {
                "val": 2,
                "text": "El crepúsculo"
            },
            {
                "val": 3,
                "text": "El bienestar"
            },
            {
                "val": 4,
                "text": "La felicidad"
            },
            {
                "val": 5,
                "text": "El ocaso"
            }
        ]
    },
    {
        "id": 55,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "55.- Escriba los dos números que faltan a esta serie: (120     100 82      66 ______ 40         30 _____ 15         12   10)",
        "opciones": [
            {
                "val": 1,
                "text": "50 y 20"
            },
            {
                "val": 2,
                "text": "54 y 24"
            },
            {
                "val": 3,
                "text": "52 y 22"
            },
            {
                "val": 4,
                "text": "52 y 20"
            },
            {
                "val": 5,
                "text": "48 y 18"
            }
        ]
    },
    {
        "id": 56,
        "area": "Información y Conocimientos Generales",
        "texto": "56.- La bitácora es de uso indispensable en:",
        "opciones": [
            {
                "val": 1,
                "text": "Música"
            },
            {
                "val": 2,
                "text": "Biología"
            },
            {
                "val": 3,
                "text": "Navegación"
            },
            {
                "val": 4,
                "text": "Teatro"
            },
            {
                "val": 5,
                "text": "Química"
            }
        ]
    },
    {
        "id": 57,
        "area": "Comprensión Verbal y Vocabulario (Opuestos)",
        "texto": "57.- Lo contrario de homogéneo es:",
        "opciones": [
            {
                "val": 1,
                "text": "Compacto"
            },
            {
                "val": 2,
                "text": "Heterogéneo"
            },
            {
                "val": 3,
                "text": "Abstracto"
            },
            {
                "val": 4,
                "text": "Sútil"
            },
            {
                "val": 5,
                "text": "Neutro"
            }
        ]
    },
    {
        "id": 58,
        "area": "Razonamiento Verbal (Discriminación Conceptual)",
        "texto": "58.- De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
        "opciones": [
            {
                "val": 1,
                "text": "Stravinski"
            },
            {
                "val": 2,
                "text": "Bach"
            },
            {
                "val": 3,
                "text": "Mozart"
            },
            {
                "val": 4,
                "text": "Newton"
            },
            {
                "val": 5,
                "text": "Chopin"
            }
        ]
    },
    {
        "id": 59,
        "area": "Razonamiento Lógico (Analogías Verbales)",
        "texto": "59.- La biblioteca es para guardar libros y la pinacoteca para guardar:",
        "opciones": [
            {
                "val": 1,
                "text": "Periódico"
            },
            {
                "val": 2,
                "text": "Discos"
            },
            {
                "val": 3,
                "text": "Películas"
            },
            {
                "val": 4,
                "text": "Monedas"
            },
            {
                "val": 5,
                "text": "Cuadros"
            }
        ]
    },
    {
        "id": 60,
        "area": "Razonamiento Numérico (Series Lógicas)",
        "texto": "60.- Escriba los números que faltan a esta serie: (6561 2187 729 ________ 81 ________ 9            3)",
        "opciones": [
            {
                "val": 1,
                "text": "243 y 27"
            },
            {
                "val": 2,
                "text": "216 y 24"
            },
            {
                "val": 3,
                "text": "270 y 30"
            },
            {
                "val": 4,
                "text": "243 y 36"
            },
            {
                "val": 5,
                "text": "180 y 27"
            }
        ]
    }
]

BARSIT_CORRECT_KEYS = {
    "1": 3,
    "2": 2,
    "3": 4,
    "4": 5,
    "5": 3,
    "6": 3,
    "7": 4,
    "8": 2,
    "9": 1,
    "10": 2,
    "11": 4,
    "12": 5,
    "13": 3,
    "14": 2,
    "15": 1,
    "16": 1,
    "17": 1,
    "18": 3,
    "19": 4,
    "20": 2,
    "21": 3,
    "22": 1,
    "23": 4,
    "24": 3,
    "25": 3,
    "26": 4,
    "27": 5,
    "28": 4,
    "29": 5,
    "30": 2,
    "31": 4,
    "32": 5,
    "33": 3,
    "34": 2,
    "35": 2,
    "36": 2,
    "37": 1,
    "38": 3,
    "39": 5,
    "40": 2,
    "41": 3,
    "42": 2,
    "43": 4,
    "44": 5,
    "45": 3,
    "46": 4,
    "47": 5,
    "48": 3,
    "49": 2,
    "50": 2,
    "51": 3,
    "52": 4,
    "53": 5,
    "54": 1,
    "55": 3,
    "56": 3,
    "57": 2,
    "58": 4,
    "59": 5,
    "60": 1
}

def ensure_barsit_definition(db):
    cursor = db.cursor()
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'BARSIT'")
    if not cursor.fetchone():
        escala_general = [
            {"val": 1, "text": "Opción 1"},
            {"val": 2, "text": "Opción 2"},
            {"val": 3, "text": "Opción 3"},
            {"val": 4, "text": "Opción 4"},
            {"val": 5, "text": "Opción 5"}
        ]
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'BARSIT',
            'BARSIT — Test Rápido de Barranquilla (Habilidad Mental)',
            'BARSIT',
            'Cognición y Capacidad Intelectual',
            'Evaluación psicométrica rápida de 60 reactivos desarrollada por Francisco del Olmo. Determina con rapidez el índice de inteligencia general, agilidad mental, aptitud para el aprendizaje y razonamiento verbal/numérico tanto en escolares (a partir de 3er grado) como en adultos.',
            'Lee con atención cada una de las siguientes preguntas y selecciona la opción correcta entre las 5 alternativas disponibles. Dispones de un tiempo estándar de 10 minutos para responder la mayor cantidad de preguntas posibles.',
            json.dumps(escala_general, ensure_ascii=False),
            json.dumps(BARSIT_ITEMS, ensure_ascii=False)
        ))
        db.commit()

def process_barsit_scoring(answers, patient_info=None):
    """
    Algoritmo de corrección y baremación cuantitativa y cualitativa del BARSIT.
    Total: 60 reactivos (1 punto por respuesta correcta).
    5 Áreas cognitivas (12 ítems cada una):
    1. Información y Conocimientos Generales
    2. Comprensión Verbal y Vocabulario (Opuestos / Antónimos)
    3. Razonamiento Verbal (Discriminación Conceptual / Término excluido)
    4. Razonamiento Lógico (Analogías Verbales)
    5. Razonamiento Numérico (Series Lógicas)
    """
    patient_info = patient_info or {}
    edad = patient_info.get('edad')
    try:
        edad = int(edad) if edad is not None else 25
    except (ValueError, TypeError):
        edad = 25

    total_score = 0
    scores_by_area = {
        1: 0, # Información
        2: 0, # Vocabulario / Opuestos
        3: 0, # Razonamiento Verbal
        4: 0, # Razonamiento Lógico / Analogías
        0: 0  # Razonamiento Numérico / Series (mod 5 == 0)
    }

    for item_id in range(1, 61):
        correct_val = BARSIT_CORRECT_KEYS.get(str(item_id))
        if correct_val is None:
            correct_val = BARSIT_CORRECT_KEYS.get(item_id)
            
        user_val = answers.get(str(item_id))
        if user_val is None:
            user_val = answers.get(f"item_{item_id}")
        if user_val is None:
            user_val = answers.get(item_id)
        
        if user_val is not None and correct_val is not None:
            try:
                if int(user_val) == int(correct_val):
                    total_score += 1
                    area_idx = item_id % 5
                    scores_by_area[area_idx] += 1
            except (ValueError, TypeError):
                pass

    # Interpretación cualitativa según baremo normativo (Francisco del Olmo)
    is_escolar = edad < 16
    
    if is_escolar:
        # Baremo Escolares
        if total_score <= 34:
            classification = "Muy Inferior / Deficiente (Escolares)"
            percentil_desc = "Percentil aproximado ≤ 10%"
        elif total_score <= 37:
            classification = "Inferior / Por debajo del promedio (Escolares)"
            percentil_desc = "Percentil aproximado 11% - 25%"
        elif total_score <= 43:
            classification = "Mediano / Promedio Normal (Escolares)"
            percentil_desc = "Percentil aproximado 26% - 75%"
        elif total_score <= 46:
            classification = "Superior (Escolares)"
            percentil_desc = "Percentil aproximado 76% - 90%"
        else:
            classification = "Excelente / Muy Superior (Escolares)"
            percentil_desc = "Percentil aproximado > 90%"
    else:
        # Baremo Adultos (Sexto grado en adelante / población general)
        if total_score <= 26:
            classification = "Muy Inferior / Deficiente (Adultos)"
            percentil_desc = "Percentil aproximado ≤ 10%"
        elif total_score <= 33:
            classification = "Inferior / Bajo Promedio (Adultos)"
            percentil_desc = "Percentil aproximado 11% - 25%"
        elif total_score <= 43:
            classification = "Mediano / Promedio Normal (Adultos)"
            percentil_desc = "Percentil aproximado 26% - 75%"
        elif total_score <= 50:
            classification = "Superior / Alto (Adultos)"
            percentil_desc = "Percentil aproximado 76% - 90%"
        else:
            classification = "Excelente / Muy Superior (Adultos)"
            percentil_desc = "Percentil aproximado > 90%"

    subscales_dict = {
        "Información y Conocimientos Generales": f"{scores_by_area[1]}/12 pts ({round(scores_by_area[1]/12*100)}%)",
        "Comprensión de Vocabulario (Opuestos)": f"{scores_by_area[2]}/12 pts ({round(scores_by_area[2]/12*100)}%)",
        "Razonamiento Verbal (Discriminación Conceptual)": f"{scores_by_area[3]}/12 pts ({round(scores_by_area[3]/12*100)}%)",
        "Razonamiento Lógico (Analogías Verbales)": f"{scores_by_area[4]}/12 pts ({round(scores_by_area[4]/12*100)}%)",
        "Razonamiento Numérico (Series Lógicas)": f"{scores_by_area[0]}/12 pts ({round(scores_by_area[0]/12*100)}%)"
    }

    baremo_grupo = "Escolares (< 16 años)" if is_escolar else "Adultos (≥ 16 años)"
    interpretation = (
        f"Puntuación Directa Total: {total_score}/60 puntos aciertos. "
        f"Nivel de Habilidad Mental: {classification} ({percentil_desc}, baremo para {baremo_grupo}). "
        f"El Test Rápido de Barranquilla (BARSIT) evalúa la capacidad intelectual global, rapidez de procesamiento cognitivo, "
        f"aptitud para el aprendizaje y adaptabilidad a nuevas tareas estructuradas. "
        f"Perfil por subáreas: Conocimientos Generales ({scores_by_area[1]}/12), Vocabulario/Antónimos ({scores_by_area[2]}/12), "
        f"Discriminación Verbal ({scores_by_area[3]}/12), Analogías Lógicas ({scores_by_area[4]}/12) y Series Numéricas ({scores_by_area[0]}/12)."
    )

    return total_score, subscales_dict, classification, interpretation
