from typing import TypeVar, Mapping, Optional
from algorithms.td_algo_enum import TDAlgorithm
from algorithms.rl_tabular.rl_tabular_base import RLTabularBase
from processes.policy import Policy
from processes.mp_funcs import get_rv_gen_func_single
from processes.mdp_rep_for_rl_tabular import MDPRepForRLTabular
from processes.mp_funcs import get_expected_action_value

S = TypeVar('S')
A = TypeVar('A')
VFType = Mapping[S, float]
QVFType = Mapping[S, Mapping[A, float]]


class TDLambda(RLTabularBase):

    def __init__(
        self,
        mdp_rep_for_rl: MDPRepForRLTabular,
        algorithm: TDAlgorithm,
        softmax: bool,
        epsilon: float,
        epsilon_half_life: float,
        learning_rate: float,
        learning_rate_decay: float,
        lambd: float,
        num_episodes: int,
        max_steps: int
    ) -> None:

        super().__init__(
            mdp_rep_for_rl=mdp_rep_for_rl,
            softmax=softmax,
            epsilon=epsilon,
            epsilon_half_life=epsilon_half_life,
            num_episodes=num_episodes,
            max_steps=max_steps
        )
        self.algorithm: TDAlgorithm = algorithm
        self.learning_rate: float = learning_rate
        self.learning_rate_decay: float = learning_rate_decay
        self.gamma_lambda = self.mdp_rep.gamma * lambd

    def get_value_func_dict(self, pol: Policy) -> VFType:
        sa_dict = self.mdp_rep.state_action_dict
        vf_dict = {s: 0. for s in sa_dict.keys()}
        act_gen_dict = {s: get_rv_gen_func_single(pol.get_state_probabilities(s))
                        for s in sa_dict.keys()}
        episodes = 0
        updates = 0

        while episodes < self.num_episodes:
            et_dict = {s: 0. for s in sa_dict.keys()}
            state = self.mdp_rep.init_state_gen()
            steps = 0
            terminate = False

            while not terminate:
                action = act_gen_dict[state]()
                next_state, reward =\
                    self.mdp_rep.state_reward_gen_dict[state][action]()
                delta = reward + self.mdp_rep.gamma * vf_dict[next_state] -\
                    vf_dict[state]
                et_dict[state] += 1
                alpha = self.learning_rate * (updates / self.learning_rate_decay
                                              + 1) ** -0.5
                for s in sa_dict.keys():
                    vf_dict[s] += alpha * delta * et_dict[s]
                    et_dict[s] *= self.gamma_lambda
                updates += 1
                steps += 1
                terminate = steps >= self.max_steps or\
                    state in self.mdp_rep.terminal_states
                state = next_state

            episodes += 1

        return vf_dict

    def get_qv_func_dict(self, pol: Optional[Policy]) -> QVFType:
        control = pol is None
        this_pol = pol if pol is not None else self.get_init_policy()
        sa_dict = self.mdp_rep.state_action_dict
        qf_dict = {s: {a: 0.0 for a in v} for s, v in sa_dict.items()}
        episodes = 0
        updates = 0

        while episodes < self.num_episodes:
            et_dict = {s: {a: 0.0 for a in v} for s, v in sa_dict.items()}
            state, action = self.mdp_rep.init_state_action_gen()
            steps = 0
            terminate = False

            while not terminate:
                next_state, reward = \
                    self.mdp_rep.state_reward_gen_dict[state][action]()
                next_action = get_rv_gen_func_single(
                    this_pol.get_state_probabilities(next_state)
                )()
                if self.algorithm == TDAlgorithm.QLearning and control:
                    next_qv = max(qf_dict[next_state][a] for a in
                                  qf_dict[next_state])
                elif self.algorithm == TDAlgorithm.ExpectedSARSA and control:
                    # next_qv = sum(this_pol.get_state_action_probability(
                    #     next_state,
                    #     a
                    # ) * qf_dict[next_state][a] for a in qf_dict[next_state])
                    next_qv = get_expected_action_value(
                        qf_dict[next_state],
                        self.softmax,
                        self.epsilon_func(episodes)
                    )
                else:
                    next_qv = qf_dict[next_state][next_action]

                delta = reward + self.mdp_rep.gamma * next_qv -\
                    qf_dict[state][action]
                et_dict[state][action] += 1
                alpha = self.learning_rate * (updates / self.learning_rate_decay
                                              + 1) ** -0.5
                for s, a_set in sa_dict.items():
                    for a in a_set:
                        qf_dict[s][a] += alpha * delta * et_dict[s][a]
                        et_dict[s][a] *= self.gamma_lambda
                updates += 1
                if control:
                    if self.softmax:
                        this_pol.edit_state_action_to_softmax(
                            state,
                            qf_dict[state]
                        )
                    else:
                        this_pol.edit_state_action_to_epsilon_greedy(
                            state,
                            qf_dict[state],
                            self.epsilon_func(episodes)
                        )
                steps += 1
                terminate = steps >= self.max_steps or \
                    state in self.mdp_rep.terminal_states
                state = next_state
                action = next_action

            episodes += 1

        return qf_dict


if __name__ == '__main__':
    from processes.mdp_refined import MDPRefined
    mdp_refined_data = {
        1: {
            'a': {1: (0.3, 9.2), 2: (0.6, 4.5), 3: (0.1, 5.0)},
            'b': {2: (0.3, -0.5), 3: (0.7, 2.6)},
            'c': {1: (0.2, 4.8), 2: (0.4, -4.9), 3: (0.4, 0.0)}
        },
        2: {
            'a': {1: (0.3, 9.8), 2: (0.6, 6.7), 3: (0.1, 1.8)},
            'c': {1: (0.2, 4.8), 2: (0.4, 9.2), 3: (0.4, -8.2)}
        },
        3: {
            'a': {3: (1.0, 0.0)},
            'b': {3: (1.0, 0.0)}
        }
    }
    gamma_val = 0.9
    mdp_ref_obj1 = MDPRefined(mdp_refined_data, gamma_val)
    mdp_rep_obj = mdp_ref_obj1.get_mdp_rep_for_rl_tabular()

    algorithm_type = TDAlgorithm.ExpectedSARSA
    softmax_flag = True
    epsilon_val = 0.1
    epsilon_half_life_val = 100
    learning_rate_val = 0.1
    learning_rate_decay_val = 1e6
    lambda_val = 0.2
    episodes_limit = 1000
    max_steps_val = 1000
    esl_obj = TDLambda(
        mdp_rep_obj,
        algorithm_type,
        softmax_flag,
        epsilon_val,
        epsilon_half_life_val,
        learning_rate_val,
        learning_rate_decay_val,
        lambda_val,
        episodes_limit,
        max_steps_val
    )

    policy_data = {
        1: {'a': 0.4, 'b': 0.6},
        2: {'a': 0.7, 'c': 0.3},
        3: {'b': 1.0}
    }
    pol_obj = Policy(policy_data)

    this_qf_dict = esl_obj.get_act_value_func_dict(pol_obj)
    print(this_qf_dict)
    this_vf_dict = esl_obj.get_value_func_dict(pol_obj)
    print(this_vf_dict)

    opt_pol = esl_obj.get_optimal_det_policy()
    print(opt_pol)
    opt_vf_dict = esl_obj.get_value_func_dict(opt_pol)
    print(opt_vf_dict)
