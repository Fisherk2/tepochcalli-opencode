# Cuaderno de cartografía orbital

Este cuaderno dorado reúne las observaciones de la misión Ícaro durante el
sobrevuelo del asteroide Vellocino. La prosa es deliberadamente larga y
continua para que el segmentador canónico —presupuesto de mil quinientos
treinta y seis bytes por chunk con ciento noventa y dos de solape— produzca
varios chunks con cita completa, de modo que el e2e de T8 pueda verificar la
identidad del slice sobre el archivo original en cada resultado que `search`
devuelva por el wire. Ninguna línea de este texto se reescribe en tiempo de
corrida: el fixture queda grabado en el repositorio y los offsets de cita se
miden sobre estos mismos bytes, sin dependencia del reloj ni de la red.

## Instrumentación del espectrómetro

El espectrómetro de partículas calibrado en la fase de crucero registra la
composición del regolito con una resolución de cuarenta canales por muestra.
Cada lectura se archiva con su marca temporal y su incertidumbre asociada,
lista para la reducción de datos que se describe en la sección siguiente. El
detector de neutrones trabaja en paralelo y comparte la ventana de
integración con el espectrómetro primario, de modo que ambas series quedan
alineadas sobre la misma referencia temporal de a bordo.

Los protocolos de calibración se ejecutan antes y después de cada pase
cerca del asteroide, y sus curvas de respuesta se guardan junto a los
datos crudos para que la reducción posterior pueda reproducirse sin
acceso al instrumento. Si una calibración queda incompleta, la misión
marca la ventana como de baja confianza en lugar de descartarla: el
catálogo final distingue explícitamente entre abundancias verificadas
y abundancias provisionales pendientes de una segunda calibración.

## Reducción de datos

La reducción aplica correcciones de fondo derivadas de las lecturas de
vacío tomadas antes y después de cada pase, y promedia las muestras
repetidas dentro de cada ventana de observación. Las rejillas de
contención se inspeccionan visualmente antes de publicar, porque un
artefacto de saturación puede imitar una línea de emisión débil y solo
la revisión manual distingue ambos casos con certeza suficiente para el
catálogo. El producto final es un catálogo de abundancias con su
intervalo de confianza, publicado junto a las tablas crudas del archivo
de misión y con la versión exacta del pipeline de reducción citada en el
encabezado de cada tabla, para que cualquier investigador pueda repetir
el cálculo desde los datos primarios sin preguntas abiertas.

## Publicación del catálogo

El catálogo publicado incluye, para cada elemento detectado, su
abundancia relativa, su incertidumbre estadística, la ventana de
observación de la que proviene y el identificador del pipeline que lo
redujo. Las notas de versión documentan cada cambio de umbral de
detección, de modo que una comparación entre catálogos de misiones
distintas pueda rastrear hasta la decisión concreta que produjo la
diferencia, en lugar de atribuirla a la instrumentación sin más.
