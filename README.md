# 📡 Multi-Device Barcode & QR Code Reader

Sistema desktop desenvolvido para captura simultânea de até **4 leitores físicos de QR Code / Código de Barras**, com registro estruturado e exportação automatizada para Excel.

Projeto voltado para cenários operacionais, industriais e logísticos onde múltiplos dispositivos precisam registrar dados simultaneamente com rastreabilidade.

---

## 🎯 Objetivo do Projeto

Criar uma solução leve, confiável e escalável para:

- Captura simultânea de múltiplos dispositivos
- Identificação da origem da leitura
- Registro com timestamp
- Organização estruturada dos dados
- Exportação automatizada

---

## 🚀 Principais Features

- 📡 Leitura simultânea de até 4 dispositivos
- 🧠 Identificação automática do leitor
- 🕒 Registro com data e hora
- 📊 Exportação para Excel (.xlsx)
- 🖥️ Interface simples e operacional
- ⚙️ Estrutura preparada para integração futura com API

---

## 🏗️ Arquitetura do Sistema

Fluxo de funcionamento:

Dispositivo → Captura → Identificação do Reader → Registro Estruturado → Exportação Excel

O sistema foi pensado para:

- Baixa latência
- Organização modular
- Fácil manutenção
- Expansão futura (API / Banco / Cloud)

---

## 🛠️ Stack Tecnológica

- Python 3.x
- Pandas
- OpenPyXL
- Tkinter (GUI)
- Captura via HID / Serial

---

## 📂 Estrutura do Projeto

reader_barcode_qrcode/
│
├── main.py
├── readers/
├── utils/
├── output/
└── README.md


---

## ⚙️ Instalação

Clone o projeto:

```bash
git clone https://github.com/Saulo-Azevedo/reader_barcode_qrcode.git
cd reader_barcode_qrcode
Crie ambiente virtual:

python -m venv venv
Ative:

Windows:

venv\Scripts\activate
Linux/Mac:

source venv/bin/activate
Instale dependências:

pip install pandas openpyxl
▶️ Executar
python main.py
📊 Exportação
Os dados são exportados contendo:

Código lido

Origem do dispositivo

Data

Hora

Arquivo gerado em:

/output/leituras.xlsx
🔮 Possíveis Evoluções
🔄 Integração com API REST

🗄️ Persistência em banco de dados (PostgreSQL)

☁️ Deploy como serviço backend

📊 Dashboard Web

🧠 Filtro inteligente de duplicidade

📡 Integração com sistemas ERP

👨‍💻 Autor
Saulo Rodrigo de Azevedo

Especialista em automação, integração de dispositivos físicos e sistemas empresariais.
Experiência em SAP, Python, integrações industriais e soluções orientadas a dados.

GitHub: https://github.com/Saulo-Azevedo
