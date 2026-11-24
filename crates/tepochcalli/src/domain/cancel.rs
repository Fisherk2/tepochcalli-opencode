//! R-offline-2: señal de cancelación compartida entre la UI y el runner.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// Token clonable: la UI lo dispara y el runner lo sondea. `Default` = vivo.
#[derive(Debug, Clone, Default)]
pub struct CancelToken(Arc<AtomicBool>);

impl CancelToken {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    /// Idempotente: varias llamadas (botón + Ctrl+C) son el mismo disparo.
    pub fn cancel(&self) {
        self.0.store(true, Ordering::SeqCst);
    }

    #[must_use]
    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }
}

#[cfg(test)]
mod tests {
    use super::CancelToken;

    /// `Default` = vivo; `cancel()` es idempotente y el clon comparte el
    /// disparo (la UI cancela, el runner sondea otra copia del mismo token).
    #[test]
    fn token_is_born_alive_and_cancels_through_clones() {
        let token = CancelToken::new();
        let arm = token.clone();
        assert!(!token.is_cancelled(), "un token nuevo está vivo");
        arm.cancel();
        assert!(token.is_cancelled(), "el clon comparte el disparo");
        token.cancel();
        assert!(arm.is_cancelled(), "cancelar dos veces es el mismo disparo");
    }
}
