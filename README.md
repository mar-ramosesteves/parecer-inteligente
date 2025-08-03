# Sistema de Pareceres Inteligentes - Microambiente de Equipes

Este sistema gera pareceres inteligentes sobre microambiente de equipes, incluindo gráficos dinâmicos inseridos automaticamente no texto do parecer.

## Funcionalidades

### ✅ Gráficos Implementados
1. **Gráfico de Dimensões da Equipe** - Mostra a percepção da equipe sobre as dimensões de microambiente
2. **Gráfico de Autoavaliação do Líder** - Mostra a autoavaliação do líder
3. **Gráfico Comparativo** - Compara a percepção da equipe com a autoavaliação do líder

### 📊 Dimensões Analisadas
- **Adaptabilidade** - Flexibilidade e aceitação de novas ideias
- **Responsabilidade** - Autonomia e delegação
- **Performance** - Foco em resultados e excelência
- **Reconhecimento** - Valorização e feedback
- **Clareza** - Objetivos e expectativas claras
- **Equipe** - Trabalho em equipe e colaboração

## Como Usar

### 1. Configuração do Ambiente
```bash
pip install -r requirements.txt
```

### 2. Variáveis de Ambiente
Configure as seguintes variáveis:
- `SUPABASE_REST_URL` - URL do seu projeto Supabase
- `SUPABASE_KEY` - Chave de API do Supabase

### 3. Executar o Sistema
```bash
python app.py
```

### 4. Endpoints Disponíveis

#### Emitir Parecer de Microambiente
```bash
POST /emitir-parecer-microambiente
```

**Payload:**
```json
{
    "empresa": "nome_empresa",
    "codrodada": "rodada_2024",
    "emailLider": "lider@empresa.com"
}
```

#### Emitir Parecer de Arquétipos
```bash
POST /emitir-parecer-arquetipos
```

## Estrutura dos Gráficos

### Inserção Automática
Os gráficos são inseridos automaticamente no texto do parecer nos seguintes pontos:

1. **"Abaixo, os gráficos de dimensões e subdimensões de microambiente na percepção de sua equipe:"**
   - Insere o gráfico de percepção da equipe

2. **"E abaixo, os gráficos de dimensões e subdimensões de microambiente na sua percepção:"**
   - Insere o gráfico de autoavaliação do líder

3. **"O inventário de Microambiente de Equipe é baseado nos conceitos de inteligência emocional."**
   - Insere o gráfico comparativo

### Formato dos Gráficos
- **Tipo**: Gráficos de barras com valores percentuais
- **Cores**: Azul para equipe, Rosa para autoavaliação
- **Escala**: 0-100%
- **Responsivo**: Adapta-se ao tamanho da tela

## Melhorias Implementadas

### ✅ Problemas Corrigidos
1. **Função faltando**: Adicionada `salvar_json_no_supabase()`
2. **Gráficos dinâmicos**: Agora busca dados reais do Supabase
3. **Inserção inteligente**: Gráficos inseridos nos pontos estratégicos do texto
4. **Formatação melhorada**: Gráficos com bordas e títulos

### 🎨 Melhorias Visuais
- Gráficos com cores profissionais
- Bordas arredondadas
- Títulos descritivos
- Responsividade para diferentes telas

## Estrutura de Dados

### Tabelas Supabase Necessárias
- `microambiente_equipe` - Dados da percepção da equipe
- `microambiente_autoavaliacao` - Dados da autoavaliação do líder
- `relatorios_gerados` - Pareceres gerados

### Campos das Tabelas
```sql
-- microambiente_equipe
empresa, codrodada, emaillider, adaptabilidade, responsabilidade, 
performance, reconhecimento, clareza, equipe

-- microambiente_autoavaliacao  
empresa, codrodada, emaillider, adaptabilidade, responsabilidade,
performance, reconhecimento, clareza, equipe
```

## Próximos Passos

### 🚀 Funcionalidades Futuras
1. **Mais tipos de gráficos**: Gráficos de pizza, linha temporal
2. **Análise de tendências**: Comparação entre rodadas
3. **Exportação**: PDF, Excel, PowerPoint
4. **Dashboard**: Interface visual para análise

### 📈 Melhorias Técnicas
1. **Cache de gráficos**: Para melhor performance
2. **Gráficos interativos**: Com Chart.js ou D3.js
3. **Filtros avançados**: Por período, equipe, dimensão

## Suporte

Para dúvidas ou problemas, verifique:
1. **Logs do servidor**: Para erros de conexão
2. **Dados no Supabase**: Se os dados estão sendo salvos corretamente
3. **Configuração**: Se as variáveis de ambiente estão corretas

---

**Desenvolvido para análise inteligente de microambiente de equipes** 🎯
