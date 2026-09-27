# Guía de Contribución

Gracias por tu interés en contribuir a ProCamera. Esta guía te ayudará a entender cómo puedes colaborar.

## 📋 Código de Conducta

Este proyecto y todos los participantes están sujetos al [Código de Conducta](CODE_OF_CONDUCT.md). Al participar, aceptas cumplir con estos términos.

## 🐛 Reportar Issues

### Bugs
1. Verifica que el issue no haya sido reportado antes
2. Usa la plantilla de issues de GitHub
3. Incluye:
   - Sistema operativo y versión
   - Versión de Python
   - Logs de error completos
   - Pasos para reproducir el error

### Sugerencias de Features
1. Describe claramente la funcionalidad deseada
2. Explica por qué sería útil
3. Si es posible, propón una implementación

## 🔧 Desarrollo

### Setup Local
```bash
# Fork y clonar
git clone https://github.com/tuusuario/ProCamera.git
cd ProCamera

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Para desarrollo
```

### Estilo de Código

* Sigue PEP 8

* Usa type hints

* Documenta funciones con docstrings

* Máximo 88 caracteres por línea (Black estándar)

### Commits

* Usa mensajes descriptivos en presente

* Referencia el issue relacionado

* Ejemplo: ``` Fix: Corregir error de conexión #42 ```

### Pull Requests

* Actualiza tu fork con los últimos cambios

* Crea una rama descriptiva

* Realiza commits pequeños y lógicos

* Asegúrate de que todas las pruebas pasen

* Describe claramente los cambios en el PR

* Referencia issues relacionados

### 🧪 Pruebas
```bash
# Ejecutar pruebas unitarias
python -m pytest

# Ejecutar con cobertura
python -m pytest --cov=.
```
### 📝 Documentación

* Actualiza el README.md si añades nuevas funcionalidades

* Documenta nuevas clases y métodos con docstrings

* Mantén el CHANGELOG.md actualizado

### 🤝 Revisión de Código

Todos los PRs requieren aprobación de al menos un mantenedor. Por favor:

- Sé respetuoso con los revisores

- Responde a los comentarios

- Realiza los cambios solicitados

***¡Gracias por contribuir a ProCamera! 🚀***


---