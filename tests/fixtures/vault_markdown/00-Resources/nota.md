# Fuentes y parseo de Markdown

Este archivo de prueba vive en la raíz indexable del vault y contiene prosa
suficiente para que `RecursiveSplitter` produzca varios chunks con el
presupuesto canónico de 1536 bytes por chunk y 192 bytes de solape. La cita de
cada chunk se deriva de los offsets de carácter sobre este mismo texto: si el
particionado es correcto, el trozo de texto que arrastra cada chunk coincide
exactamente con el rango que declaran sus offsets.

## Whitelist de extensiones

El flujo indexa únicamente los archivos cuya extensión está en la whitelist
canónica: `.md`, `.markdown`, `.txt` y `.pdf`. Cualquier otro archivo que el
investigador deposite en el recurso —imágenes exportadas por el navegador,
binarios de instrumentación, notas de Obsidian con formato propietario, o
cualquier artefacto que la herramienta de captura decida volcar en la carpeta—
queda fuera del índice sin abortar el pase de indexación. La whitelist vive en
un único lugar del código, de modo que ampliarla en el futuro (por ejemplo con
`.docx` vía markitdown, según el fallback documentado en la spec de
markitdown) es un cambio localizado y no una cacería de patrones dispersos.

El diseño de la whitelist es deliberadamente corta: cada extensión admitida
tiene una ruta de parseo conocida y una semántica de cita conocida. Markdown y
texto plano se leen directamente; el PDF pasa por Docling en modo CPU y
conserva la jerarquía de headings del documento original, lo que mejora la
precisión de las citas sobre artículos académicos.

## Exclusiones y segmentos con punto

Los directorios y archivos cuyo nombre empieza por punto son materiales
internos de Obsidian, de git o del propio sistema de indexación: `.obsidian/`
contiene la configuración de la aplicación, `.git/` el historial de versiones
y carpetas ocultas como `.oculto/` pueden contener material que el usuario
depositó sabiendo que nadie lo leería. Indexarlos sería un fallo de
privacidad, no solo de rendimiento, y por eso la exclusión es explícita en el
matchear de rutas: los patrones de inclusión por sí solos no bastan, porque el
globset subyacente considera que un asterisco casa también los segmentos que
empiezan por punto. La prueba de esta capa afirma que un archivo dentro de un
directorio oculto jamás aparece en la salida del walk.

El anidamiento libre es otro contrato de esta capa. La investigadora organiza
el recurso como quiere: carpetas por tema, por año, por fuente bibliográfica,
con acentos y con espacios si así lo desea. Esa organización no se aplana ni
se renombra: la ruta relativa completa viaja con cada chunk como metadato de
cita, de modo que una respuesta del agente puede remitir exactamente al
archivo y a la sección de donde salió.

## Derivación de citas

Cada chunk arrastra cinco campos de cita. La ruta fuente, en forma POSIX y con
el prefijo del recurso; el tipo de documento derivado de la extensión; el
último heading de nivel ATX que precede al offset de inicio, que puede ser
nulo cuando el documento no tiene jerarquía —un archivo de texto plano nunca
tendrá heading padre—; los offsets de inicio y fin dentro del texto extraído;
y el identificador del modelo de embeddings con que se vectorizó el chunk, que
permite detectar índices mixtos cuando se cambia de modelo. La identidad del
slice se verifica en caliente: el texto del chunk debe ser exactamente el
trozo que indican sus offsets, sin recortes silenciosos ni expand.

El solape entre chunks consecutivos cubre las frases que caen en el borde de
un corte. Con 192 bytes de solape sobre un presupuesto de 1536 bytes, cada
frase partida entre dos chunks queda entera en al menos uno de ellos, y el
coste adicional de índice ronda el catorce por ciento. Medir en bytes y no en
caracteres es una decisión deliberada: el presupuesto de memoria del índice y
la expansión UTF-8 del español —con sus tildes y la eñe— se comportan de
forma predecible cuando la unidad es el byte.
