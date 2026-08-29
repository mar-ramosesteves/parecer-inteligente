# Precalculo executivo LeaderTrack

Este documento descreve a camada persistente da devolutiva executiva. Ela existe para que CEO, RH e diretoria recebam graficos e HTML rapidamente depois do encerramento de uma rodada, sem depender de uma chamada extensa ao bot.

## O que entra no Supabase

- Uma execucao identifica uma combinacao unica de rodada, contexto, filtros, regras de amostra e versao de calculo.
- Um pacote guarda o resultado calculado completo, usado pelo dashboard e pelo caderno HTML.
- Cruzamentos ficam em linhas separadas para permitir carregar somente a camada solicitada.
- Insights de IA ficam em linhas separadas por tema. Uma falha em saude emocional nao invalida arquétipos ou microambiente.

## Fluxo de producao

1. Um administrador seleciona a rodada na tela LeaderTrack e usa o botao `Gerar snapshots executivos`.
2. O comando administrativo descobre dinamicamente todas as empresas com consolidados naquela rodada. Nao existe lista fixa de empresas no backend.
3. O processamento cria um snapshot por empresa e um snapshot adicional para o contexto atualmente selecionado.
4. Cada snapshot calcula base geral e cruzamentos autorizados com N minimo. Nos recortes demograficos, as autoavaliacoes de todos os lideres sao preservadas e somente as respostas das equipes sao filtradas.
5. O resultado e gravado como pacote concluido. Empresas com amostra insuficiente recebem um registro de controle sem scores nem recortes exibiveis.
6. A IA recebe camadas pequenas e as salva separadamente. Ela nunca recebe respostas individuais brutas.
7. Dashboard e caderno HTML leem o pacote concluido. O bot so e chamado quando um insight ainda nao existe ou quando o administrador pede regeneracao.

## Regras de privacidade

- Nenhum cruzamento com amostra inferior ao minimo configurado e gravado como insight exibivel.
- O pacote mantem apenas metricas agregadas; respostas individuais permanecem nas fontes existentes, sem duplicacao.
- As quatro tabelas possuem RLS e nao concedem acesso para `anon` ou `authenticated`.
- Somente o dashboard e o bot, configurados no Render com `SUPABASE_SERVICE_ROLE_KEY`, poderao le-las ou grava-las.
- O botao administrativo usa uma chave compartilhada somente entre WordPress e Render. A chave nunca e enviada ao navegador.
- Reexecucoes com a mesma origem e versao atualizam o mesmo pacote; uma mudanca real nas fontes gera um novo hash auditavel.
- Para manter o banco leve, os snapshots de todas as empresas guardam somente a leitura geral. Os recortes detalhados sao gravados apenas para o contexto selecionado.
- Cada contexto armazena no maximo 40 recortes elegiveis, priorizados por familia e tamanho de amostra. A tabela separada de cruzamentos fica reservada para uma fase futura e nao e preenchida nesta versao.

## Recortes iniciais do contexto

- Departamento e cargo versus contexto selecionado.
- Genero e etnia versus contexto selecionado.
- Genero x etnia.
- Saude emocional, microambiente e arquetipos para os mesmos recortes quando houver N minimo.

Combinacoes de tres dimensoes e cruzamentos empresa x atributo nao sao precalculados. Caso sejam necessarios no futuro, devem ser gerados sob demanda e com expiracao definida.
