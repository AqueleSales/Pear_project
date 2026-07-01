# 🍐 Pear Project - Server Launcher

Um sistema de orquestração e Launcher em Python para servidores de Minecraft, focado em facilidade de uso, túneis TCP dinâmicos e, futuramente, integração com arquitetura em nuvem.

## 🚀 Tecnologias Utilizadas
* **Backend:** Python (PySide6 para a interface gráfica, FastAPI para a nuvem).
* **Infraestrutura:** Ngrok (Túnel TCP), Java 25.
* **Motor do Jogo:** PaperMC (Versão 26.1).

## ⚙️ Pré-requisitos
1. [Java 25 (Eclipse Temurin)](https://adoptium.net/) instalado (Certifique-se de configurar a variável `JAVA_HOME`).
2. Python 3.10+
3. Conta no [Ngrok](https://ngrok.com/) com um Authtoken válido.

## 🔐 Configuração do Ambiente Local
Por questões de segurança, as chaves de API não estão versionadas. Você deve criar um arquivo `.env` na raiz do projeto:

1. Crie o arquivo `.env` com o seguinte formato:
    ```text
    NGROK_TOKEN=seu_token_ngrok_aqui
    API_KEY=sua_api_key_da_nuvem
    ```
2. Instale as dependências do projeto:
    ```bash
    pip install -r requirements.txt
    ```

## 🔌 Configurações do Servidor Minecraft (Versão 26.1)
Este projeto usa a versão otimizada do **PaperMC**. Para garantir que todos consigam jogar, algumas configurações são necessárias na pasta do perfil (ex: `perfis/vanilla/`):

* **Jogadores Originais e Piratas Juntos:**
  No arquivo `server.properties`, a propriedade `online-mode` deve ser definida como `false`.
* **Restauração de Skins:**
  Como o `online-mode` está desativado, é necessário utilizar o plugin **SkinRestorer**. Baixe o `.jar` do plugin no site do Modrinth/Spigot e coloque-o na pasta `perfis/vanilla/plugins/`. Os jogadores originais terão a skin carregada automaticamente.

## 🏃 Como Iniciar
1. Suba a API no terminal principal: `uvicorn nomad_api:app --host 0.0.0.0 --port 5000`
2. No segundo terminal, inicie a interface: `python launcher_desktop.py`
3. Preencha o nickname, clique em **INICIAR SERVIDOR** e copie o IP fornecido pelo Ngrok na tela.