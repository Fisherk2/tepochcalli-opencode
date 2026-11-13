---
title: Optimización de bucles en LLVM
date: 2026-11-12
tags: [compiladores, llvm]
---

# Optimización de bucles en LLVM

La representación intermedia de LLVM conserva la forma de los bucles para que las
pasadas puedan transformarlos: vectorización, desenrollado e intercambio de
iteraciones se aplican sobre la misma estructura canónica. Cada pasada declara
qué análisis conserva y cuál invalida, y el gestor de pasadas lo respeta.

## Vectorización y análisis de alias

La vectorización de bucles necesita probar que dos punteros no se solapan; el
análisis de alias responde esa pregunta y su respuesta conservadora deja el bucle
escalar. Añadir `restrict` a los parámetros convierte la duda en una promesa que
el programador firma, y con ella el vectorizador emite instrucciones SIMD.

El desenrollado se decide por coste: duplicar el cuerpo reduce el salto pero
presiona la caché de instrucciones, y el umbral no es el mismo para un núcleo de
servidor que para uno móvil.
