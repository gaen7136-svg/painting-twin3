import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time

st.set_page_config(page_title="YULfactory: 고속 최적화 관제", layout="wide")

# --- [1. 데이터 초기화] ---
if 'workers' not in st.session_state:
    ids = [f'W_{i+1:02d}' for i in range(30)]
    levels = ['전문가']*5 + ['숙련공']*15 + ['신입']*10
    np.random.shuffle(levels)
    st.session_state.workers = pd.DataFrame({
        'ID': ids, 'Level': levels,
        'Skill_Weight': [1.2 if l == '전문가' else 1.0 if l == '숙련공' else 0.7 for l in levels],
        'Condition': 1.0, 'Cum_Exp': 0.0, 'Work_Time': 0.0,
        'is_present': True, 'Status': '대기'
    })
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}
    st.session_state.log = ["🚀 시스템 가동 시작"]

# --- [2. 사이드바: 정적 렌더링 (한 번만 그림)] ---
with st.sidebar:
    st.header("🕹️ 실시간 제어판")
    
    # 컨디션 조절
    on_duty_ids = st.session_state.workers[st.session_state.workers['Status'] == '근무']['ID'].tolist()
    target = st.selectbox("컨디션 하락 타겟", on_duty_ids if on_duty_ids else ["없음"])
    if st.button("⚠️ 즉시 컨디션 저하"):
        st.session_state.workers.loc[st.session_state.workers['ID'] == target, 'Condition'] = 0.2
        st.toast(f"{target} 위급 상황 발생!")

    st.divider()
    st.subheader("🏬 출근 현황")
    # 성능을 위해 30개 체크박스를 컬럼으로 나누어 배치
    for i in range(30):
        w = st.session_state.workers.iloc[i]
        cb = st.checkbox(f"{w['ID']} ({w['Level']})", value=w['is_present'], key=f"p_{w['ID']}")
        if cb != st.session_state.workers.at[i, 'is_present']:
            st.session_state.workers.at[i, 'is_present'] = cb
            st.session_state.workers.at[i, 'Status'] = '대기' if cb else '퇴근'
            st.rerun() # 설정 변경 시에만 리런

# --- [3. 메인 관제 로직 (Fragment 사용하여 부분 갱신)] ---
@st.fragment(run_every=1.5) # 1.5초마다 맵과 로그만 '부분적으로' 새로 고침
def update_dashboard():
    # A. 인력 교체 로직
    workers = st.session_state.workers
    
    # 퇴출 (시간/컨디션/미출근)
    to_exit = workers[(workers['Status'] == '근무') & 
                      ((workers['Work_Time'] >= 8.0) | (workers['Condition'] < 0.4) | (~workers['is_present']))]
    for idx in to_exit.index:
        st.session_state.workers.at[idx, 'Status'] = '퇴근'
        st.session_state.log.append(f"🚨 {workers.at[idx, 'ID']} 교체됨")

    # 무한 리셋
    if len(workers[(workers['Status'] == '대기') & (workers['is_present'])]) < 5:
        st.session_state.workers.loc[(st.session_state.workers['Status'] == '퇴근') & (workers['is_present']), ['Work_Time', 'Status', 'Condition']] = [0.0, '대기', 1.0]
        st.session_state.log.append("♻️ 사이클 리셋")

    # 투입 (10명 유지)
    current_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무']
    if len(current_duty) < 10:
        needed = 10 - len(current_duty)
        available = st.session_state.workers[(st.session_state.workers['Status'] == '대기') & (workers['is_present'])].iloc[:needed]
        for idx in available.index:
            st.session_state.workers.at[idx, 'Status'] = '근무'

    # B. 맵 그리기
    on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].head(10)
    if not on_duty.empty:
        voc_matrix = np.random.randint(10, 100, (2, 5))
        # (비용 계산 및 헝가리안 알고리즘 생략 가능 시 단순 매칭으로 더 빠르게 가능하나 유지)
        row_ind, col_ind = linear_sum_assignment(np.random.rand(len(on_duty), 10)) # 속도를 위해 랜덤 매칭 예시

        col_left, col_right = st.columns([2.5, 1])
        with col_left:
            fig = go.Figure(go.Heatmap(z=voc_matrix, colorscale='RdYlGn_r', opacity=0.4, showscale=False))
            for i, (r, c) in enumerate(zip(row_ind, col_ind)):
                w = on_duty.iloc[r]
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5
                fig.add_trace(go.Scatter(x=[c], y=[r], mode="markers+text",
                    marker=dict(size=40, color=st.session_state.colors[w['ID']], line=dict(width=3, color='white' if w['Condition']>0.5 else 'red')),
                    text=f"<b>{w['ID']}</b>", textposition="middle center"))
            fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        with col_right:
            st.caption("최근 로그")
            for l in st.session_state.log[-5:]: st.write(f"· {l}")
            st.dataframe(on_duty[['ID', 'Condition', 'Work_Time']], hide_index=True)

st.title("🛡️ YULfactory: 최적화 관제")
update_dashboard()
