import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.integrate import odeint
from scipy.optimize import minimize
import math
from scipy.stats import binom as binom

from smoothing import dataframe_smoothing




class SEIR():

    def __init__(self):

        # ========================================== #
        #           Model parameters
        # ========================================== #
        self.beta = 0.3         # Contamination rate
        self.sigma = 0.8        # Incubation rate
        self.gamma = 0.15       # Recovery rate
        self.hp = 0.05          # Hospit rate
        self.hcr = 0.2          # Hospit recovery rate
        self.pc = 0.1           # Critical rate
        self.pd = 0.1           # Critical recovery rate
        self.pcr = 0.3          # Critical mortality
        self.s = 0.765          # Sensitivity
        self.t = 0.75           # Testing rate in symptomatical

        # Learning set
        self.dataframe = None
        self.dataset = None

        # Initial state
        self.I_0 = 2                        # Infected
        self.E_0 = 3                        # Exposed
        self.R_0 = 0                        # Recovered
        self.S_0 = 1000000 - self.I_0 - self.E_0      # Sensible
        self.H_0 = 0
        self.C_0 = 0
        self.D_0 = 0
        self.CT_0 = self.I_0                # Contamined

        # ========================================== #
        #        Hyperparameters dashboard:
        # ========================================== #

        # Importance given to each curve during the fitting process
        self.w_1 = 0.7          # Weight of cumulative positive data
        self.w_2 = 0.3          # Weight of positive data
        self.w_3 = 0.7          # Weight of hopit data
        self.w_4 = 0.3          # Weight of cumul hospit data
        self.w_5 = 1            # Weight àf critical data
        self.w_6 = 1            # Weight of fatalities data

        # Value to return if log(binom.pmf(k,n,p)) = - infinity
        self.overflow = - 1000

        # Smoothing data or not
        self.smoothing = False

        # Binomial smoother: ex: if = 2: predicted value *= 2 and p /= 2 WARNING: only use integer
        self.b_s_1 = 6
        self.b_s_2 = 2
        self.b_s_3 = 6
        self.b_s_4 = 2
        self.b_s_5 = 4
        self.b_s_6 = 4

        # Optimizer step size
        self.opti_step = 0.05

        # Optimizer constraints
        self.beta_min = 0.1
        self.beta_max = 0.9
        self.sigma_min = 1/5
        self.sigma_max = 1
        self.gamma_min = 1/10
        self.gamma_max = 1/4
        self.hp_min = 0.01
        self.hp_max = 0.5
        self.hcr_min = 0.01
        self.hcr_max = 0.4
        self.pc_min = 0.01
        self.pc_max = 0.4
        self.pd_min = 0.01
        self.pd_max = 0.5
        self.pcr_min = 0.01
        self.pcr_max = 0.4
        self.s_min = 0.7
        self.s_max = 0.85
        self.t_min = 0.5
        self.t_max = 1

        # Optimizer choise:
        self.cobyla = True
        self.LBFGSB = False
        self.auto = False

    def get_parameters(self):

        prm = (self.beta, self.sigma, self.gamma, self.hp, self.hcr, self.pc, self.pd, self.pcr, self.s, self.t)
        return prm

    def get_initial_state(self):

        I_0 = self.dataset[0][1]
        H_0 = self.dataset[0][3]
        E_0 = I_0
        D_0 = 0
        C_0 = 0
        S_0 = 1000000 - I_0 - H_0 - E_0
        R_0 = 0
        CT_0 = I_0
        CH_0 = H_0
        init = (S_0, E_0, I_0, R_0, H_0, C_0, D_0, CT_0, CH_0)
        return init

    def differential(self, state, time, beta, sigma, gamma, hp, hcr, pc, pd, pcr, s, t):

        S, E, I, R, H, C, D, CT, CH = state

        dS = -(beta * S * I) / (S + I + E + R + H + C + D)
        dE = ((beta * S * I) / (S + I + E + R + H + C + D)) - (sigma * E)
        dI = (sigma * E) - (gamma * I) - (hp * I)
        dH = (hp * I) - (hcr * H) - (pc * H)
        dC = (pc * H) - (pd * C) - (pcr * C)
        dD = (pd * C)
        dR = (gamma * I) + (hcr * H) + (pcr * C)

        dCT = sigma * E
        dCH = hp * I

        return dS, dE, dI, dR, dH, dC, dD, dCT, dCH

    def predict(self, duration, initial_state=None, parameters=None):

        # Time vector:
        time = np.arange(duration)
        # Parameters to use
        prm = parameters
        if prm is None:
            prm = self.get_parameters()
        # Initial state to use:
        init = initial_state
        if init is None:
            init = self.get_initial_state()

        # Make prediction:
        predict = odeint(func=self.differential,
                         y0=init,
                         t=time,
                         args=(tuple(prm)))
        return predict

    def fit(self):

        # Initial values of parameters:
        init_prm = (self.beta, self.sigma, self.gamma, self.hp, self.hcr, self.pc, self.pd, self.pcr, self.s, self.t)
        # Initial state:
        init_state = self.get_initial_state()
        # Time vector:
        time = self.dataset[:, 0]
        # Bounds
        bds = [(self.beta_min, self.beta_max), (self.sigma_min, self.sigma_max), (self.gamma_min, self.gamma_max),
               (self.hp_min, self.hp_max), (self.hcr_min, self.hcr_max), (self.pc_min, self.pc_max),
               (self.pd_min, self.pd_max), (self.pcr_min, self.pcr_max), (self.s_min, self.s_max),
               (self.t_min, self.t_max)]
        # Constraint on parameters:
        cons = ({'type': 'ineq', 'fun': lambda x: -x[0] + self.beta_max},
                {'type': 'ineq', 'fun': lambda x: -x[1] + self.sigma_max},
                {'type': 'ineq', 'fun': lambda x: -x[2] + self.gamma_max},
                {'type': 'ineq', 'fun': lambda x: -x[3] + self.hp_max},
                {'type': 'ineq', 'fun': lambda x: -x[4] + self.hcr_max},
                {'type': 'ineq', 'fun': lambda x: -x[5] + self.pc_max},
                {'type': 'ineq', 'fun': lambda x: -x[6] + self.pd_max},
                {'type': 'ineq', 'fun': lambda x: -x[7] + self.pcr_max},
                {'type': 'ineq', 'fun': lambda x: -x[8] + self.s_max},
                {'type': 'ineq', 'fun': lambda x: -x[9] + self.t_max},
                {'type': 'ineq', 'fun': lambda x: x[0] - self.beta_min},
                {'type': 'ineq', 'fun': lambda x: x[1] - self.sigma_min},
                {'type': 'ineq', 'fun': lambda x: x[2] - self.gamma_min},
                {'type': 'ineq', 'fun': lambda x: x[3] - self.hp_min},
                {'type': 'ineq', 'fun': lambda x: x[4] - self.hcr_min},
                {'type': 'ineq', 'fun': lambda x: x[5] - self.pc_min},
                {'type': 'ineq', 'fun': lambda x: x[6] - self.pd_min},
                {'type': 'ineq', 'fun': lambda x: x[7] - self.pcr_min},
                {'type': 'ineq', 'fun': lambda x: x[8] - self.s_min},
                {'type': 'ineq', 'fun': lambda x: x[9] - self.t_min})

        # Optimizer
        res = None
        if self.LBFGSB:
            res = minimize(self.objective, np.asarray(init_prm),
                           method='L-BFGS-B',
                           args=('method_1'),
                           bounds=bds)
        else:
            if self.cobyla:
                res = minimize(self.objective, np.asarray(init_prm),
                               method='COBYLA',
                               options={'eps': self.opti_step},
                               args=('method_1'),
                               constraints=cons)
            else:   # Auto
                res = minimize(self.objective, np.asarray(init_prm),
                               constraints=cons,
                               options={'eps': self.opti_step},
                               bounds=bds)


        # Print optimizer result
        print(res)
        # Update model parameters:
        self.beta = res.x[0]
        self.sigma = res.x[1]
        self.gamma = res.x[2]
        self.hp = res.x[3]
        self.hcr = res.x[4]
        self.pc = res.x[5]
        self.pd = res.x[6]
        self.pcr = res.x[7]
        self.s = res.x[8]
        self.t = res.x[9]

    def objective(self, parameters, method, print_details=False):

        if method == 'method_1':
            # Here we try to maximise the probability of each observations
            # Make predictions:
            params = tuple(parameters)
            pred = self.predict(duration=self.dataset.shape[0],
                                parameters=params)
            # Uncumul contaminations
            conta = []
            conta.append(pred[0][7])
            for i in range(0, pred.shape[0]):
                conta.append(pred[i][7] - pred[i-1][7])

            # Compare with dataset:
            prb = 0
            print(params)
            for i in range(0, pred.shape[0]):
                p_k1 = p_k2 = p_k3 = p_k4 = p_k5 = p_k6 = self.overflow
                # ======================================= #
                # PART 1: Fit on cumul positive test
                # ======================================= #
                pa = params[8] * params[9]
                n = np.around(pred[i][7] * pa)
                k = self.dataset[i][7]
                p = 1 / self.b_s_1
                if k < 0 and n < 0:
                    k *= -1
                    n *= -1
                if k > n:
                    tmp = n
                    n = k
                    k = tmp
                if k < 0:
                    k = 1
                    n += k + 1
                n *= self.b_s_1
                prob = binom.pmf(k=k, n=n, p=p)
                if prob > 0:
                    p_k1 = np.log(binom.pmf(k=k, n=n, p=p))
                else:
                    p_k1 = self.overflow
                prb -= p_k1 * self.w_1

                # ======================================= #
                # PART 2: Fit on positive test
                # ======================================= #
                pa = params[8] * params[9]
                n = np.around(conta[i] * pa)
                k = self.dataset[i][1]
                p = 1 / self.b_s_2
                if k < 0 and n < 0:
                    k *= -1
                    n *= -1
                if k > n:
                    tmp = n
                    n = k
                    k = tmp
                if k < 0:
                    k = 1
                    n += k + 1
                n *= self.b_s_2
                prob = binom.pmf(k=k, n=n, p=p)
                if prob > 0:
                    p_k2 = np.log(binom.pmf(k=k, n=n, p=p))
                else:
                    p_k2 = self.overflow
                prb -= p_k2 * self.w_2

                # ======================================= #
                # PART 3: Fit on hospit
                # ======================================= #
                n = np.around(pred[i][4])
                k = self.dataset[i][3]
                p = 1 / self.b_s_3
                if k < 0 and n < 0:
                    k *= -1
                    n *= -1
                if k > n:
                    tmp = n
                    n = k
                    k = tmp
                if k < 0:
                    k = 1
                    n += k + 1
                n *= self.b_s_3
                prob = binom.pmf(k=k, n=n, p=p)
                if prob > 0:
                    p_k3 = np.log(binom.pmf(k=k, n=n, p=p))
                else:
                    p_k3 = self.overflow
                prb -= p_k3 * self.w_3

                # ======================================= #
                # PART 4: Fit on cumul hospit
                # ======================================= #
                n = np.around(pred[i][8])
                k = self.dataset[i][4]
                p = 1 / self.b_s_4
                if k < 0 and n < 0:
                    k *= -1
                    n *= -1
                if k > n:
                    tmp = n
                    n = k
                    k = tmp
                if k < 0:
                    k = 1
                    n += k + 1
                n *= self.b_s_4
                prob = binom.pmf(k=k, n=n, p=p)
                if prob > 0:
                    p_k4 = np.log(binom.pmf(k=k, n=n, p=p))
                else:
                    p_k4 = self.overflow
                prb -= p_k4 * self.w_4

                # ======================================= #
                # Part 5: Fit on Critical
                # ======================================= #
                n = np.around(pred[i][5])
                k = self.dataset[i][5]
                p = 1 / self.b_s_5
                if k < 0 and n < 0:
                    k *= -1
                    n *= -1
                if k > n:
                    tmp = n
                    n = k
                    k = tmp
                if k < 0:
                    k = 1
                    n += k + 1
                n *= self.b_s_5
                prob = binom.pmf(k=k, n=n, p=p)
                if prob > 0:
                    p_k5 = np.log(binom.pmf(k=k, n=n, p=p))
                else:
                    p_k5 = self.overflow
                prb -= p_k5 * self.w_5

                # ======================================= #
                # Part 6: Fit on Fatalities
                # ======================================= #
                n = np.around(pred[i][6])
                k = self.dataset[i][6]
                p = 1 / self.b_s_6
                if k < 0 and n < 0:
                    k *= -1
                    n *= -1
                if k > n:
                    tmp = n
                    n = k
                    k = tmp
                if k < 0:
                    k = 1
                    n += k + 1
                n *= self.b_s_6
                prob = binom.pmf(k=k, n=n, p=p)
                if prob > 0:
                    p_k6 = np.log(binom.pmf(k=k, n=n, p=p))
                else:
                    p_k6 = self.overflow
                prb -= p_k6 * self.w_6

                if print_details:
                    print('iter {}: {} - {} - {} - {} - {} - {}'.format(i, p_k1, p_k2, p_k3, p_k4, p_k5, p_k6))
                    print('test+ cumul: {} - {}'.format(np.around(pred[i][7] * params[8] * params[9]), self.dataset[i][7]))
                    print('test+: {} - {}'.format(np.around(conta[i] * params[8] * params[9]), self.dataset[i][1]))
                    print('hospit: {} - {}'.format(np.around(pred[i][4]), self.dataset[i][3]))
                    print('hospit cumul: {} - {}'.format(np.around(pred[i][8]), self.dataset[i][4]))
                    print('critical: {} - {}'.format(np.around(pred[i][5]), self.dataset[i][5]))
                    print('Fatalities: {} - {}'.format(np.around(pred[i][6]), self.dataset[i][6]))

            print(prb)

            return prb



    def import_dataset(self):

        url = "https://raw.githubusercontent.com/ADelau/proj0016-epidemic-data/main/data.csv"
        # Import the dataframe:
        raw = pd.read_csv(url, sep=',', header=0)
        raw['num_positive'][0] = 1
        # Ad a new column at the end with cumulative positive cases at the right
        cumul_positive = raw['num_positive'].to_numpy()
        raw.insert(7, 'cumul_positive', cumul_positive)
        if self.smoothing:
            self.dataframe = dataframe_smoothing(raw)
        else: self.dataframe = raw
        self.dataset = self.dataframe.to_numpy()

        self.I_0 = self.dataset[0][1] / (self.s * self.t)
        self.E_0 = self.I_0 * 5
        self.R_0 = 0
        self.S_0 = 1000000 - self.I_0 - self.E_0

    def sensib_finder(self):

        range_size = 50
        sensib_range = np.linspace(0.1, 1, range_size)
        print(sensib_range)

        accuracies = []

        init_state = self.get_initial_state()
        best = (math.inf, 0)

        for j in range(0, range_size):

            self.s = sensib_range[j]
            self.fit()

            # Compute error:
            error = 0.0
            params = (self.beta, self.sigma, self.gamma, self.s)
            pred = self.predict(duration=self.dataset.shape[0],
                                parameters=params)
            # Compare with dataset:
            prb = 0
            print(params)
            for i in range(0, pred.shape[0]):
                p = params[-1]
                p /= 2
                n = round(pred[i][4] * 2)
                k = round(self.dataset[i][1])


                p_k = np.log(binom.pmf(k=k, n=n, p=p))
                if p_k == - math.inf or math.isnan(p_k):
                    p_k = -1000
                prb += p_k
            accuracies.append(-prb)
            if -prb < best[0]:
                best = (-prb, sensib_range[j])
            print('iter {} / {}'.format(j, range_size))

        plt.plot(sensib_range, accuracies, c='blue')
        plt.show()
        print('best sensib = {} with error = {}'.format(best[1], best[0]))
        self.s = best[1]


if __name__ == "__main__":

    # Create the model:
    model = SEIR()
    # Import dataset:
    model.import_dataset()

    # Fit:
    model.fit()

    params = model.get_parameters()
    #model.objective(params, 'method_1', print_details=True)




    # Make a prediction:
    prd = model.predict(model.dataset.shape[0])
    for i in range(0, prd.shape[0]):
        prd[i][3] = prd[i][3] * model.s * model.t

    print('=== For cumul positif: ')
    for i in range(0, 10):
        print('dataset: {}, predict = {}'.format(model.dataset[i, 7], prd[i][7]))
    print('=== For hospit: ')
    for i in range(0, 10):
        print('dataset: {}, predict = {}'.format(model.dataset[i, 3], prd[i][4]))
    print('===  E values: ')
    print(prd[:, 1])

    # Plot
    plt.scatter(model.dataset[:, 0], model.dataset[:, 7], c='blue', label='testing data')
    plt.scatter(model.dataset[:, 0], model.dataset[:, 3], c='green', label='hospit')
    plt.plot(model.dataset[:, 0], prd[:, 4], c='yellow', label='hospit pred')
    plt.plot(model.dataset[:, 0], prd[:, 7], c='red', label='predictions')
    plt.legend()
    plt.show()

    plt.scatter(model.dataset[:, 0], model.dataset[:, 5], c='blue', label='critical data')
    plt.plot(model.dataset[:, 0], prd[:, 5], c='red', label='critical prediction')
    plt.scatter(model.dataset[:, 0], model.dataset[:, 6], c='yellow', label='dead data')
    plt.plot(model.dataset[:, 0], prd[:, 6], c='green', label='dead predict')
    plt.legend()
    plt.show()

    for i in range(0, model.dataset.shape[0]):
        print('critical pred vs deaad pred: {} : {}'.format(prd[i][5], prd[i][6]))



