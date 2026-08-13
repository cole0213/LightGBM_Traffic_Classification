# 🧠 [마스터 가이드] Transformer ──▶ BERT ──▶ ET-BERT 완벽 정복

> **노션(Notion) 정리용 서식**으로 작성된 문서입니다. 노션 페이지에 그대로 복사(`Ctrl+C` -> `Ctrl+V`)하여 사용하실 수 있습니다.

---

## 📌 전체 학습 로드맵 요약

$$\text{1단계: 딥러닝/NLP 기초} \longrightarrow \text{2단계: Transformer (Self-Attention)} \longrightarrow \text{3단계: BERT 핵심} \longrightarrow \text{4단계: ET-BERT 응용}$$

---

# 1단계: 딥러닝 & NLP 입문 기초 (Prerequisites)

### 1. 토큰(Token)과 토큰화
* **개념**: 컴퓨터는 문자열을 직접 이해하지 못하므로, 텍스트를 최소 의미 단위인 **조각(Token)**으로 쪼갠 뒤 고유한 **숫자 번호(Token ID)**로 변환함.
* **예시**:
  * 원문: `"나는 딥러닝을 공부한다"`
  * 서브워드 토큰화: `["나", "##는", "딥", "##러닝", "##을", "공부", "##한다"]`
  * 토큰 ID 변환: `[105, 3421, 882, 9123, 401, ...]`

### 2. 임베딩(Embedding): 수치 좌표 변환
* **개념**: 단순 숫자 번호를 의미가 포함된 **고차원 공간상의 좌표(벡터)**로 변환하는 기술.
* **특징**: 의미가 유사한 단어일수록 공간상에서 서로 **가까운 거리(유사도)**에 위치함.
  * 예: $\text{Vector}(\text{"사과"}) \approx \text{Vector}(\text{"바나나"})$ (과일 관계)
  * BERT-Base 기준 각 토큰은 **768차원 수치 벡터**로 변환됨.

### 3. 딥러닝 학습의 4단계 루프
```text
[1. 입력 (Input)]  ──▶  [2. 예측 (Forward)]  ──▶  [3. 오차 계산 (Loss)]  ──▶  [4. 가중치 수정 (Optimizer)]
   텍스트 텐서                모델 출력 예측             정답과 비교해 오차 계산          Loss를 줄이는 방향으로 가중치 수정
```

---

# 2단계: Transformer & Self-Attention 원리

### 1. 기존 RNN / LSTM의 한계
1. **병렬 처리 불가**: 단어를 한 번에 하나씩 순차적으로 읽어야 하므로 GPU 병렬 연산 불가능 (속도 매우 느림).
2. **장기 의존성 (Long-Term Dependency) 정보 손실**: 문장이 길어지면 앞단어의 정보가 뒤로 갈수록 휘발됨.

### 2. Transformer의 혁신: Self-Attention
> *"순서대로 읽지 말고 512개 단어를 한 번에 통째로 쏟아넣고, 단어들끼리 연관성(Attention)을 계산하자!"*

### 3. Query, Key, Value (Q, K, V) 3대 요소
* **Query ($Q$)**: "내가 지금 집중해서 찾고 있는 질문 단어"
* **Key ($K$)**: "비교 대상 단어들의 식별표"
* **Value ($V$)**: "단어가 가지고 있는 실제 정보 수치"

### 4. Self-Attention 수식과 연산 4단계

$$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$

| 단계 | 연산 과정 | 설명 |
| :--- | :--- | :--- |
| **1. 점수 계산** | $Q \cdot K^T$ | 문장 안의 모든 단어쌍 간 유사도 점수 계산 |
| **2. 스케일링** | $\div \sqrt{d_k}$ | 수치가 너무 커져 그래디언트가 터지는 것 방지 ($\sqrt{64}=8$) |
| **3. Softmax** | $\text{softmax}(\dots)$ | 점수의 총합이 $1.0(100\%)$이 되도록 확률값으로 변환 |
| **4. V 혼합** | $\times V$ | 확률에 따라 각 단어의 Value 정보를 혼합하여 문맥 벡터 완성 |

### 5. Positional Encoding (위치 정보)
* 단어를 한 번에 병렬 연산하므로 순서 정보가 사라짐.
* 단어 임베딩 벡터에 **위치 고유 파형 신호(Positional Encoding Vector)**를 더해서 순서 정보를 부여함.

---

# 3단계: BERT 특화 개념 (BERT Architecture)

### 1. WordPiece 토큰화 (서브워드 분할)
* 단어를 더 작은 조각(`##`)으로 쪼개서 사전(Vocab)에 없는 모르는 단어(**OOV: Out-of-Vocabulary**) 문제 완벽 해결.
* 예: `unaffordability` $\rightarrow$ `["un", "##afford", "##ability"]`

### 2. BERT의 특수 토큰 4대장
* `[CLS]` (Classification): **문장 맨 앞(0번)** 위치. 문장 전체 의미를 압축하여 **문장 분류 Task**에 사용.
* `[SEP]` (Separator): 문장 끝 또는 문장 A/B 간 구분선.
* `[MASK]` (Mask): 사전 학습 시 단어를 가리는 덮개.
* `[PAD]` (Padding): 512 길이를 맞추기 위해 빈 공간을 채우는 0번 토큰.

### 3. 사전 학습(Pre-training) 2가지 미션

$$\text{Total Pre-training Loss} = \mathcal{L}_{MLM} + \mathcal{L}_{NSP}$$

1. **MLM (Masked Language Model)**:
   * 입력 토큰의 15%를 무작위 선택하여 `[MASK]` 처리 후, 양방향 문맥을 보고 원래 단어 예측 (Cross-Entropy Loss).
2. **NSP (Next Sentence Prediction)**:
   * 두 문장을 주고 "B가 A 바로 뒤에 오는 문장인가?" (`IsNext` vs `NotNext`) 이진 분류 (Binary Cross-Entropy Loss).

### 4. 미세 조정 (Fine-tuning)
* 사전 학습된 거대 가중치(Pre-trained Weights)를 다운로드함.
* 맨 위 `[CLS]` 위치에 분류용 **Linear Layer(Head)** 하나만 붙여 내 데이터셋으로 빠르게 재학습(보통 2~4 Epoch).

---

# 4단계: ET-BERT (암호화 트래픽 분석 응용)

### 1. HuggingFace 기본 파이썬 구조
```python
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# 1. 토크나이저 및 사전학습 모델 불러오기
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=2)

# 2. 텍스트 토큰화 ([input_ids], [attention_mask] 생성)
inputs = tokenizer("I love deep learning", return_tensors="pt")

# 3. 예측 (Forward Pass)
outputs = model(**inputs)
predictions = torch.argmax(outputs.logits, dim=-1)
```

### 2. ET-BERT (Encrypted Traffic BERT) 매핑

| 자연어 BERT | ET-BERT (네트워크 트래픽 분석) |
| :--- | :--- |
| **자연어 텍스트 문장** | **Datagram Burst (연속된 패킷 흐름/페이로드)** |
| **WordPiece 단어 토큰** | **2Byte 단위 Hex 스트림 토큰** (예: `["4500", "003c", "a1b2"]`) |
| **MLM (단어 가리기)** | **패킷 바이트 마스킹** (특정 페이로드 위치 `[MASK]` 후 원래 바이트 예측) |
| **문장 감정 분류** | **악성 트래픽 분류 / 앱(서비스) 프로토콜 분류** |

---

### 📝 핵심 요약 한눈에 보기
1. **Transformer**: Q, K, V의 **Self-Attention** 연산으로 긴 문장의 양방향 문맥을 병렬로 처리함.
2. **BERT**: Transformer Encoder 위에 **WordPiece + `[CLS]` + MLM/NSP**로 언어 구조를 사전 학습함.
3. **ET-BERT**: 자연어 단어 대신 **네트워크 Hex 패킷 페이로드**를 토큰화하여 암호화 트래픽을 분류함.
