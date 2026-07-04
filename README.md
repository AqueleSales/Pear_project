
```
# 🍐 Pear Project - Super Launcher

Um sistema de orquestração e Launcher em Python para servidores de Minecraft, focado em facilidade de uso, túneis TCP dinâmicos e integração com arquitetura em nuvem descentralizada. O objetivo do Pear Project é permitir uma hospedagem P2P fluida, onde qualquer jogador pode assumir a rede e continuar o mundo de onde parou.

---

## 🚀 Tecnologias Utilizadas

* **Backend & Orquestração:** Python (PySide6 para a interface gráfica nativa, FastAPI para a nuvem).
* **Infraestrutura de Rede:** Ngrok (Túnel TCP Reverso), Integração Nativa SSH (Paramiko).
* **Motor do Jogo:** PaperMC (Versão 26.1).
* **Ambiente de Execução:** Java 25.

---

## ⚙️ Pré-requisitos

* **Java 25** (Eclipse Temurin) instalado (Certifique-se de configurar a variável `JAVA_HOME`).
* **Python 3.10+**
* Conta no **Ngrok** com um Authtoken válido.

---

## 🔐 Configuração do Ambiente Local

Por questões de segurança cibernética, as chaves de API e arquivos de infraestrutura não estão versionados no GitHub. 

1. Você deve criar um arquivo `.env` na raiz do projeto com o seguinte formato:
   ```env
   NGROK_TOKEN=seu_token_ngrok_aqui
   API_KEY=sua_api_key_da_nuvem

```

2. Instale as dependências do projeto:
```bash
pip install -r requirements.txt

```



---

## 🔌 Configurações do Servidor Minecraft (Versão 26.1)

Este projeto usa a versão otimizada do PaperMC acoplada a um proxy Velocity na nuvem. Para garantir a autenticação híbrida, algumas configurações são exigidas na pasta do perfil (ex: `perfis/vanilla/`):

* **Autenticação Híbrida (Originais e Piratas):** No arquivo `server.properties` e no `paper-global.yml`, a propriedade `online-mode` deve ser definida obrigatoriamente como `false`. O Launcher já aplica injeções automáticas para garantir essa blindagem.
* **Restauração de Skins:** Como o `online-mode` está desativado, o ecossistema utiliza o plugin **SkinsRestorer**. Baixe o `.jar` do plugin e coloque-o na pasta `perfis/vanilla/plugins/` (e também na pasta de plugins do Velocity na Oracle). Jogadores originais terão a skin carregada automaticamente, e jogadores offline podem utilizar o comando `/skin`.

---

## 🏃 Como Iniciar

1. Suba a API no terminal principal (Nuven/Local):
```bash
uvicorn nomad_api:app --host 0.0.0.0 --port 5000

```


2. No segundo terminal, inicie a interface gráfica do Launcher:
```bash
python launcher_desktop.py

```


3. Preencha seu nickname, escolha o modo de conexão e clique em **HOSPEDAR E JOGAR** ou **APENAS CONECTAR**. A orquestração cuidará do resto!

---

## 🗺️ Roadmap de Produção (V2.0 e Além)

O projeto está em evolução contínua para se tornar um sistema autossustentável de nível Enterprise. As próximas etapas de desenvolvimento incluem:

### 1. O Ecossistema de Skins Híbrido

* **UI de Guarda-Roupa (Drag & Drop):** Área interativa no PySide6 onde o jogador offline arrasta o seu arquivo `.png` de skin.
* **Banco de Dados/API:** Armazenamento do perfil do usuário via Firebase ou SQLite, com upload invisível de imagens (Imgur/MineSkin API).
* **Auto-Injeção de Assets:** O launcher lê o banco de dados e seta a skin via SSH/RCON direto na Oracle no momento do login.

### 2. Infraestrutura de Rede e Orquestração

* **Migração da API para a Nuvem:** O motor de orquestração se torna um backend Oracle, e o launcher vira um *Thin Client*, removendo a necessidade de distribuir chaves `.key` de SSH.
* **Health-Check de Túneis (Heartbeat):** Monitoramento contínuo. Se o Ngrok do Host apresentar instabilidade, o sistema tenta a reconexão automática sem derrubar o Java.
* **Failover de Host:** Inteligência na API que avisa a rede caso o servidor principal fique offline, liberando a vaga de hospedagem.

### 3. Gestão de Persistência (O "Save Universal")

* **Sincronização em Background (Deltas):** Compressão inteligente que faz upload apenas dos arquivos modificados do mundo para a nuvem.
* **Sistema de Trava (Locking):** Implementação de um `server.lock` no storage para impedir que dois amigos hospedem e corrompam o mesmo mapa simultaneamente.
* **Passagem de Bastão (Host Migration):** Transferência de hospedagem fluida entre os usuários conectados.
* **Garbage Collector de Nuvem:** Limpeza automatizada de backups antigos no S3/Drive.

### 4. Launcher UX/UI (Experiência do Usuário)

* **Auto-Update Remoto:** Consulta de `version.json` para download transparente de novas versões do `.exe`.
* **Gerenciamento Dinâmico de Memória:** Escaneamento de hardware para alocação inteligente da flag `-Xmx` baseada na RAM ociosa do Host.
* **Pré-carregamento Inteligente:** Download em background dos binários do PaperMC durante a navegação.

### 5. Gestão de Recursos e Analytics

* **Monitoramento de TPS:** Alertas visuais na interface se o processamento do PC do Host começar a gargalar (TPS < 15).
* **Gamificação P2P:** Sistema de créditos ou tags no servidor para os usuários que passarem mais tempo segurando a hospedagem (Uptime).

```

```