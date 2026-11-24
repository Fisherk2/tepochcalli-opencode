//! Step 6 del swap D8.4 (T16): purga del cache del modelo anterior.
//!
//! Extraído de `swap.rs` al cruzar su umbral de líneas (CODE_STYLE §Umbral):
//! es una responsabilidad cerrada — borrar los slug dirs HF del modelo viejo
//! **solo** tras el commit atómico, sin tocar el modelo nuevo ni los decoys
//! del esquema antiguo.

use std::path::{Path, PathBuf};

use super::installer::RUNTIME_DIR;

/// Model cache dir, sandboxed under the vault (same dir the F6 gate uses).
const MODELS_DIR: &str = "models";

/// Step 6: purge the previous model cache — only after the atomic switch, and
/// never with `--keep-previous`, never when old == new. Targets the HF slug
/// dirs (`models--<id con / → -->`, más el gemelo `sentence-transformers`)
/// bajo `models/` y `models/hub/`; los nombres planos del esquema antiguo son
/// decoys y se conservan. Las candidatas del modelo nuevo nunca se tocan.
pub(super) fn gc_old_model(
    vault: &Path,
    old: Option<String>,
    new: Option<&str>,
    keep_previous: bool,
) {
    if keep_previous {
        return;
    }
    let (Some(old_model), Some(new_model)) = (old, new) else {
        return;
    };
    if old_model == new_model || new_model.is_empty() {
        return;
    }
    let protected = gc_candidate_dirs(new_model);
    for root in model_cache_roots(vault) {
        for name in gc_candidate_dirs(&old_model) {
            if protected.contains(&name) {
                continue;
            }
            remove_cache_entry(&root.join(name));
        }
    }
}

/// Slug dirs HF de un model id: `models--<id con / → -->`, más el gemelo con
/// prefijo `sentence-transformers` (en ambas direcciones: un id escueto
/// comparte caché con su forma `sentence-transformers/...` y viceversa).
fn gc_candidate_dirs(model: &str) -> Vec<String> {
    let slug = model.replace('/', "--");
    let mut out = vec![format!("models--{slug}")];
    const ST: &str = "sentence-transformers--";
    if let Some(rest) = slug.strip_prefix(ST) {
        let bare = format!("models--{rest}");
        if bare != out[0] {
            out.push(bare);
        }
    } else {
        out.push(format!("models--{ST}{slug}"));
    }
    out
}

/// Raíces del cache de modelos bajo el vault (`HF_HOME`/`SENTENCE_TRANSFORMERS_HOME`).
fn model_cache_roots(vault: &Path) -> [PathBuf; 2] {
    let base = vault.join(RUNTIME_DIR).join(MODELS_DIR);
    [base.clone(), base.join("hub")]
}

/// Borra una entrada de caché (dir slug HF o archivo suelto); ausente ⇒ nada.
fn remove_cache_entry(path: &Path) {
    match std::fs::symlink_metadata(path) {
        Ok(meta) if meta.is_dir() => {
            let _ = std::fs::remove_dir_all(path);
        }
        Ok(_) => {
            let _ = std::fs::remove_file(path);
        }
        Err(_) => {}
    }
}

#[cfg(test)]
mod tests {
    use super::{gc_candidate_dirs, model_cache_roots};
    use std::path::Path;

    #[test]
    fn gc_candidate_dirs_covers_slash_and_flat_ids() {
        assert_eq!(
            gc_candidate_dirs("org/model"),
            vec![
                "models--org--model".to_string(),
                "models--sentence-transformers--org--model".to_string()
            ]
        );
        assert_eq!(
            gc_candidate_dirs("all-MiniLM-L6-v2"),
            vec![
                "models--all-MiniLM-L6-v2".to_string(),
                "models--sentence-transformers--all-MiniLM-L6-v2".to_string()
            ]
        );
    }

    #[test]
    fn gc_candidate_dirs_maps_the_sentence_transformers_twin_both_ways() {
        let st = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
        let dirs = gc_candidate_dirs(st);
        assert_eq!(
            dirs,
            vec![
                "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2".to_string(),
                "models--paraphrase-multilingual-MiniLM-L12-v2".to_string()
            ]
        );
        // El gemelo inverso: un id escueto protege también su forma ST.
        let bare = gc_candidate_dirs("paraphrase-multilingual-MiniLM-L12-v2");
        assert_eq!(bare.len(), 2);
        assert_eq!(
            bare[1],
            format!(
                "models--sentence-transformers--{}",
                bare[0].trim_start_matches("models--")
            )
        );
    }

    #[test]
    fn model_cache_roots_point_at_models_and_its_hub() {
        let vault = Path::new("/v");
        let roots = model_cache_roots(vault);
        assert_eq!(roots[0], vault.join(".tepochcalli").join("models"));
        assert_eq!(
            roots[1],
            vault.join(".tepochcalli").join("models").join("hub")
        );
    }
}
