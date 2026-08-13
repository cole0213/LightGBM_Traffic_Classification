# 🛡️ [마스터 가이드] Transformer ──▶ BERT ──▶ ET-BERT 완벽 정복

> **노션(Notion) 정리용 서식**으로 작성된 최종 마스터 문서입니다. 노션 페이지에 그대로 복사(`Ctrl+C` $\rightarrow$ `Ctrl+V`)하여 바로 사용하실 수 있습니다.

---

## 📌 전체 학습 로드맵 요약

$$\text{1단계: Transformer (원리/뼈대)} \longrightarrow \text{2단계: BERT (자연어 응용)} \longrightarrow \text{3단계: ET-BERT (네트워크 보안 응용)}$$

---

# 🏛️ 1단계: Transformer & Self-Attention 원리

### 1. Transformer의 등장 배경 (Attention Is All You Need, 2017)
* **기존 RNN / LSTM의 한계**:
  1. **병렬 처리 불가**: 단어를 순차적으로 읽어야 하므로 GPU 병렬 연산이 불가능해 속도가 매우 느림.
  2. **장기 의존성 (Long-Term Dependency) 정보 손실**: 문장이 길어지면 앞단어의 정보가 뒤로 갈수록 휘발됨.
* **Transformer의 혁신**: 순차 연산(RNN)을 완전히 제거하고, 512개 단어를 한 번에 통째로 쏟아넣어 **Self-Attention** 연산으로 문맥을 파악함.

### 2. Transformer 전체 구조 (Encoder-Decoder)
```text
[입력 문장]  ──▶  [인코더 (Encoder x6)]  ──(Context Vector)──▶  [디코더 (Decoder x6)]  ──▶  [출력 생성]
"I am a student"     문장 전체 의미 압축                          다음 단어를 하나씩 예측         "나는 학생입니다"
```
* **인코더 (Encoder)**: 양방향 문맥 파악 및 의미 압축 (BERT의 뼈대)
* **디코더 (Decoder)**: 미래 단어 마스킹 + 인코더 정보 참조를 통한 단어 생성 (GPT의 뼈대)

### 3. Self-Attention 3대 요소 (Q, K, V)
* **Query ($Q$)**: "내가 지금 집중해서 찾고자 하는 질문 단어"
* **Key ($K$)**: "비교 대상 단어들의 식별표"
* **Value ($V$)**: "단어가 가지고 있는 실제 정보 수치"

$$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$

| 연산 단계 | 수식/동작 | 설명 |
| :--- | :--- | :--- |
| **1. 점수 계산** | $Q \cdot K^T$ | 문장 안의 모든 단어쌍 간 유사도 점수 계산 |
| **2. 스케일링** | $\div \sqrt{d_k}$ | 점수가 너무 커져 그래디언트가 터지는 것 방지 ($\sqrt{64}=8$) |
| **3. Softmax** | $\text{softmax}(\dots)$ | 점수의 총합이 $1.0(100\%)$이 되도록 확률값 변환 |
| **4. V 혼합** | $\times V$ | 확률에 따라 각 단어의 Value 정보를 혼합하여 문맥 벡터 생성 |

### 4. 인코더 및 디코더 핵심 세부 부품

#### ① Positional Encoding
* 단어를 한 번에 병렬 처리하므로 순서 정보가 사라짐.
* 삼각함수 파형 수치 벡터를 단어 임베딩에 더해서 **단어의 위치(순서) 감각**을 부여함.

#### ② FFN (Feed-Forward Network)
```text
Input (768차원) ──▶ [Linear 1] ──▶ 3072차원 뻥튀기 ──▶ [GELU/ReLU] ──▶ [Linear 2] ──▶ Output (768차원)
```
* Self-Attention의 선형(Linear) 정보 혼합에 **비선형 활성화 함수(GELU)**를 적용하여 고차원 특징을 깊게 재구성함.

#### ③ Masked Self-Attention (디코더 전용)
* 디코더가 학습 시 정답 단어를 훔쳐보지 못하게, **현재 위치보다 뒤에 있는 미래 단어 위치를 마스킹(Score = $-\infty$)**함.

#### ④ Encoder-Decoder Cross-Attention (디코더 전용)
* 디코더가 단어를 생성할 때, **인코더가 넘겨준 원문 정보($K, V$)**를 참조하여 정답 단어를 정확히 추론함.

#### ⑤ EOS 토큰 (`<EOS>`)
* **End of Sequence**: 무한히 생성을 반복하는 디코더에게 **"문장이 끝났으니 생성을 멈춰라"**라고 알려주는 종료 특수 토큰.

---

# 🤖 2단계: BERT 특화 개념 (BERT Architecture)

### 1. WordPiece 토큰화 (서브워드 분할)
* 단어를 더 작은 조각(`##`)으로 쪼개서 사전에 없는 모르는 단어(**OOV: Out-of-Vocabulary**) 문제 해결.
* 예: `unaffordability` $\rightarrow$ `["un", "##afford", "##ability"]`

### 2. BERT의 특수 토큰 4대장
* `[CLS]` (Classification): **문장 맨 앞(0번)** 위치. 문장 전체 의미를 압축하여 **문장 분류 Task**에 사용.
* `[SEP]` (Separator): 문장 끝 또는 문장 A/B 간 구분선.
* `[MASK]` (Mask): 사전 학습 시 단어를 가리는 덮개.
* `[PAD]` (Padding): 512 길이를 맞추기 위해 빈 공간을 채우는 0번 토큰.

### 3. 사전 학습(Pre-training) 2가지 미션

$$\text{Total Pre-training Loss} = \mathcal{L}_{MLM} + \mathcal{L}_{NSP}$$

1. **MLM (Masked Language Model)**:
   * 입력 토큰의 15%를 무작위 선택하여 `[MASK]` 처리 후, 양방향 문맥을 보고 원래 단어 예측 (**Cross-Entropy Loss**).
2. **NSP (Next Sentence Prediction)**:
   * 두 문장을 주고 "B가 A 바로 뒤에 오는 문장인가?" (`IsNext` vs `NotNext`) 이진 분류 (**Binary Cross-Entropy Loss**).

### 4. 미세 조정 (Fine-tuning)
* 사전 학습된 거대 가중치(Pre-trained Weights)를 다운로드함.
* 맨 위 `[CLS]` 위치에 분류용 **Linear Layer(Head)** 하나만 붙여 내 데이터셋으로 빠르게 재학습(보통 2~4 Epoch).

---

# 🛡️ 3단계: ET-BERT (암호화 트래픽 분석 응용)

### 1. ET-BERT의 핵심 개념
* **정의**: 자연어(영어/한국어) 대신 **네트워크 암호화 패킷 페이로드(Hex-Byte 스트림)**를 입력받아 학습하도록 개조된 BERT 모델 (WWW 2022 논문).

### 2. 패킷 전처리 및 토큰화 3단계

```text
[1. 헤더 마스킹 (Header Cleansing)]  ──▶  [2. 2-Byte Hex 토큰화]  ──▶  [3. Datagram Burst]
 IP/Port/MAC 등 편향 유발 정보 제거         0x45 0x00 ──▶ "4500"        연속된 패킷을 [CLS], [SEP]으로
                                          (총 65,536개 전용 Vocab)        연결해 512 길이 문장 생성
```

1. **헤더 마스킹 (Header Anonymization)**:
   * IP 주소, MAC 주소, 포트 번호 등 특정 시스템의 고유 정보는 **과적합(Overfitting/Bias)**을 일으키므로 제거하거나 `0x00`으로 무력화함.
2. **2-Byte Hex 토큰화**:
   * Raw Byte `0x45 0x00` $\rightarrow$ 토큰 `"4500"`
   * $2^{16} = 65,536$개의 가능한 조합으로 ET-BERT 전용 Vocab 구축.
3. **Datagram Burst (패킷 묶어서 문장 구성)**:
   * 동일한 세션(Flow)의 연속된 패킷들을 묶어서 512 길이의 단일 문장으로 직렬화.
   * `[CLS] 4500 003c a1b2 [SEP] 4500 0040 b3c4 [SEP] [PAD] ...`

### 3. ET-BERT 사전 학습 & 미세 조정 (Fine-tuning)

#### ① MLM 사전 학습
* 무작위 마스킹된 Hex 바이트 `[MASK]`를 앞뒤 문맥 연산으로 맞히면서 정상 트래픽의 프로토콜/바이트 구조 패턴 완벽 체득.

#### ② Fine-tuning 2대 핵심 실무 Task
```text
                               ┌──▶ [Task 1: 악성 트래픽 분류]  ──▶  정상 / 트로이목마 / 랜섬웨어 / 봇넷
최종 출력 [CLS] (B, 768) ──────┤
                               └──▶ [Task 2: 암호화 앱 분류]    ──▶  유튜브 / 넷플릭스 / 카카오톡 / 토렌트
```
1. **악성 트래픽 분류 (Malware Traffic Classification)**:
   * 페이로드가 암호화되어 있어도 악성코드 특유의 통신 바이트 패턴을 잡아내어 바이러스/랜섬웨어/봇넷 여부 파악.
2. **암호화 서비스/앱 분류 (Encrypted App Classification)**:
   * 내용물이 안 보이는 TLS/HTTPS 통신이라도 바이트 형태만으로 유튜브, 넷플릭스, Tor 우회 통신 등을 정확히 식별.

### 4. 대표 벤치마크 데이터셋
* **USTC-TFC2016**: 정상 트래픽 10종 + 악성 트래픽 10종 PCAP 데이터셋.
* **ISCXTor2016**: Tor 익명망 우회 트래픽 분류 평가 데이터셋.

---

### 📊 자연어 BERT vs ET-BERT 1:1 최종 비교표

| 비교 항목 | 자연어 BERT | ET-BERT (Encrypted Traffic BERT) |
| :--- | :--- | :--- |
| **입력 데이터** | 자연어 텍스트 문장 | 네트워크 PCAP 데이터의 Datagram Burst (패킷 흐름) |
| **토큰화 방식** | WordPiece (단어/서브워드) | **2-Byte Hex 스트림 토큰화** (`"4500"`, `"003c"`) |
| **단어장(Vocab) 크기** | 약 30,522개 | **65,536개** ($2^{16}$ Hex 조합) + 특수 토큰 |
| **사전 학습 (MLM)** | 가려진 단어 `[MASK]` 예측 | **가려진 패킷 바이트 `[MASK]` 예측** |
| **주요 Fine-tuning** | 감정 분석, 질문 답변, 문서 분류 | **악성 트래픽 식별, 암호화 앱/프로토콜 분류** |
