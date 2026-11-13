# benchmarks/ — datos de trabajo de las mediciones

Directorio **local**, no versionado (todo lo de aquí está en `.gitignore` salvo este
README). Solo contiene lo que un bench **materializa en disco**: vaults temporales,
copias de corpus, índices. Son artefactos desechables de 10-150 M; se pueden borrar sin
perder nada.

Reparto de responsabilidades, para no confundir tres cosas que se llaman parecido:

| Qué | Dónde |
| --- | --- |
| **Código** de los benches | `tests/benchmarks/` |
| **Evidencia** publicada (informe + JSON con n, método, host y comando) | `docs/diagnosis/` |
| **Datos de trabajo** (vaults, corpus copiados, índices) | `benchmarks/` ← aquí |

Regla: si un fichero de aquí sirve para reproducir una cifra de `docs/`, **no** se
commitea — se commitea el comando y el JSON de resultado, que es lo que la jerarquía de
evidencia (D8: `medido > estimado > declarado`) exige.
