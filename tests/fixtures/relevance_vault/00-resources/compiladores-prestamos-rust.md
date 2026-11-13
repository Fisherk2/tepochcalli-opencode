---
title: Préstamos y tiempos de vida en Rust
date: 2026-11-12
tags: [compiladores, rust]
---

# Préstamos y tiempos de vida en Rust

El verificador de préstamos de Rust impide que un valor se lea mientras otro
préstamo lo modifica. La regla es de aliasing: muchos préstamos compartidos o uno
exclusivo, nunca ambos a la vez sobre el mismo dato. El compilador deduce los
tiempos de vida de las referencias y rechaza el programa cuando no puede probar
que ninguna referencia sobrevive a su dueño.

## El borrow checker y los tiempos de vida no léxicos

Los tiempos de vida no léxicos acortan el préstamo hasta su último uso real, y
por eso un patrón que antes exigía un bloque extra ahora compila tal cual. El
error típico que queda es el préstamo que cruza una llamada que necesita el
dueño en préstamo exclusivo: la solución es reordenar, no clonar.

Anotar un tiempo de vida en una firma es una promesa al llamador, no una señal
de que el compilador necesite ayuda.
