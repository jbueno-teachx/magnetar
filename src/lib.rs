use pyo3::prelude::*;

/// Add two integers (Rust implementation).
#[pyfunction]
fn add(a: i64, b: i64) -> i64 {
    a + b
}

/// A Python module implemented in Rust.
#[pymodule]
fn _magnetar(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(add, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
