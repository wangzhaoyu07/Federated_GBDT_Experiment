from datetime import datetime
import os
import shutil
import unittest
import torch
import numpy as np
from homo_decision_tree.homo_decision_tree_arbiter import HomoDecisionTreeArbiter
from worker import Worker
from preprocess import get_test_data


class ParameterServer(HomoDecisionTreeArbiter):
    def __init__(self, feature_num, boosting_round, booster_dim, bin_num, learning_rate, max_depth, testworkdir,
                 resultdir, modeldir):
        super().__init__()
        self.all_workers = []
        self.workers = []
        self.global_bin_split_points = []
        self.feature_num = feature_num
        self.boosting_round = boosting_round
        self.booster_dim = booster_dim
        self.bin_num = bin_num
        self.learning_rate = learning_rate
        self.max_depth = max_depth

        self.testworkdir = testworkdir
        self.RESULT_DIR = resultdir
        self.modeldir = modeldir
        self.test_data = get_test_data()
        print(self.test_data)
        # self.test_data_loader = get_test_loader()
        self.label_distribution = []

        self.group_id = 0
        self.group_num = 1  # 12
        self.predictions = []

    def treeEnsemble(self, pred_results):
        print("Start to aggregate.")
        result = []
        for i in range(0, len(pred_results)):
            valid_pred = [a for a in pred_results[i] if a != 13]
            if len(valid_pred) != 0:
                result.append(np.argmax(np.bincount(valid_pred)))
            else:
                result.append(13)
        with open(os.path.join('result', 'result.txt'), 'w') as fout:
            fout.writelines(os.linesep.join([str(n) for n in result]))

    def save_prediction(self, predition):
        if isinstance(predition, (np.ndarray,)):
            predition = predition.reshape(-1).tolist()

        with open(os.path.join(self.RESULT_DIR, 'result.txt'), 'w') as fout:
            fout.writelines(os.linesep.join([str(n) for n in predition]))

    def save_testdata_prediction(self):

        prediction = []
        predictions = self.predictions
        for rid in range(len(predictions[0])):
            predict = []
            for i in range(len(predictions)):
                predict.append(predictions[i][rid])
            prediction.append(np.argmax(np.bincount(predict)))
        self.save_prediction(prediction)

    def ensemble(self):
        for i in range(self.group_num):
            self.workers = []
            for uid in self.label_distribution[i]:
                print(self.all_workers[uid].count_label())
                self.workers.append(self.all_workers[uid])
            self.aggregate()
            loader = torch.utils.data.DataLoader(
                self.test_data,
                batch_size=75,
                shuffle=False,
            )
            test_data = []
            with torch.no_grad():
                for data in loader:
                    data = np.array(data)
                    test_data.extend(data)
            test_data = np.array(test_data)
            self.predictions.append(self.predict_data(test_data.tolist()))

    def build(self, workers):
        label_dict = {}
        # self.label_distribution = [[] for i in range(self.group_num)]
        self.label_distribution = [[0,1,2,3,4] ]
        for worker in workers:
            u_id, c = worker.count_label()
            for key, value in c.items():
                if key in label_dict:
                    label_dict[key].append(u_id)
                else:
                    label_dict[key] = [u_id]

        print(label_dict)

        '''for key, value in label_dict.items():
            for i in range(self.group_num):
                self.label_distribution[i].append(value[i])'''
        print(self.label_distribution)

        print(self.workers)

        self.all_workers = workers
        print('user number is:{}'.format(len(self.all_workers)))

    def get_quantile(self):
        global_quantile = self.workers[0].fit_get_quantile()
        for worker in self.workers[1:]:
            summary_list = worker.fit_get_quantile()
            for fid in range(len(global_quantile)):
                global_quantile[fid].merge(summary_list[fid])
        # with ProcessPoolExecutor() as executor:
        #    futures = [executor.submit(worker.fit_get_quantile) for worker in self.workers[1:]]
        #    for future in as_completed(futures):
        #        summary_list = future.result()
        #        for fid in range(len(global_quantile)):
        #            global_quantile[fid].merge(summary_list[fid])
        self.global_bin_split_points = []
        percent_value = 1.0 / self.bin_num

        percentile_rate = [i * percent_value for i in range(1, self.bin_num)]
        percentile_rate.append(1.0)
        for sum_obj in global_quantile:
            split_point = []
            for percent_rate in percentile_rate:
                s_p = sum_obj.query(percent_rate)
                if s_p not in split_point:
                    split_point.append(s_p)
            self.global_bin_split_points.append(split_point)
        print(self.global_bin_split_points)

    def get_all_histogram(self, class_idx, dep):
        left_node_histogram = self.workers[0].fit_aggregate_local_h(class_idx, dep)
        for worker in self.workers[1:]:
            worker_loacl_h = worker.fit_aggregate_local_h(class_idx, dep)
            for nid, node in enumerate(worker_loacl_h):
                # left_node_histogram[nid].merge_hist(worker_loacl_h[nid])
                feature_hist1 = left_node_histogram[nid].bag
                feature_hist2 = worker_loacl_h[nid].bag
                assert len(feature_hist1) == len(feature_hist2)
                for j in range(len(feature_hist1)):
                    assert len(feature_hist1[j]) == len(feature_hist2[j])
                    for k in range(len(feature_hist1[j])):
                        assert len(feature_hist1[j][k]) == 3
                        feature_hist1[j][k][0] += feature_hist2[j][k][0]
                        feature_hist1[j][k][1] += feature_hist2[j][k][1]
                        feature_hist1[j][k][2] += feature_hist2[j][k][2]
        # with ProcessPoolExecutor() as executor:
        #    futures = [executor.submit(worker.fit_aggregate_local_h, class_idx, dep) for worker in self.workers[1:]]
        #    for future in as_completed(futures):
        #        worker_loacl_h = future.result()
        #        for nid, node in enumerate(worker_loacl_h):
        #            # left_node_histogram[nid].merge_hist(worker_loacl_h[nid])
        #            feature_hist1 = left_node_histogram[nid].bag
        #            feature_hist2 = worker_loacl_h[nid].bag
        #            assert len(feature_hist1) == len(feature_hist2)
        #            for j in range(len(feature_hist1)):
        #                assert len(feature_hist1[j]) == len(feature_hist2[j])
        #                for k in range(len(feature_hist1[j])):
        #                    assert len(feature_hist1[j][k]) == 3
        #                    feature_hist1[j][k][0] += feature_hist2[j][k][0]
        #                    feature_hist1[j][k][1] += feature_hist2[j][k][1]
        #                    feature_hist1[j][k][2] += feature_hist2[j][k][2]

        # ??????????????????histogram
        all_histograms = self.histogram_subtraction(left_node_histogram, self.stored_histograms)
        return all_histograms

    def aggregate(self):
        print('start aggregate')
        # ??????Quantile sketch???????????????????????????
        self.get_quantile()
        # ?????????worker???????????????
        for worker in self.workers:
            worker.fit_init(self.global_bin_split_points)
        for epoch_idx in range(self.boosting_round):
            print('epoch:{}'.format(epoch_idx))

            # ???worker?????????booster?????????????????????
            for worker in self.workers:
                if (epoch_idx >= 1):
                    worker.choose_valid_feature_data()
                worker.fit_booster_init()
            for class_idx in range(self.booster_dim):
                print('class:{}'.format(class_idx))
                # ?????????label??????????????????????????????
                g_sum, h_sum = 0, 0
                for worker in self.workers:
                    # ?????????????????????
                    worker.fit_tree_init(class_idx)
                    # ????????????worker??????epoch???class????????????g h
                    g, h = worker.fit_aggregate_g_h(class_idx)
                    g_sum += g
                    h_sum += h
                # ????????????g h??????????????????worker
                for worker in self.workers:
                    worker.fit_distribute_global_g_h(class_idx, g_sum, h_sum)

                tree_height = self.max_depth + 1  # non-leaf node height + 1 layer leaf
                for dep in range(tree_height):
                    print("The depth is {}".format(dep))
                    if dep + 1 == tree_height:
                        # ??????????????????
                        for worker in self.workers:
                            worker.fit_tree_stop(class_idx)
                        break
                    cur_layer_node_num = self.workers[0].fit_cur_layer_node_num(class_idx)
                    for worker in self.workers[1:]:
                        assert worker.fit_cur_layer_node_num(class_idx) == cur_layer_node_num

                    layer_stored_hist = {}
                    all_histograms = self.get_all_histogram(class_idx, dep)
                    # store histogram
                    for hist in all_histograms:
                        layer_stored_hist[hist.hid] = hist
                    best_splits = self.federated_find_best_split(all_histograms, parallel_partitions=10)
                    self.stored_histograms = layer_stored_hist

                    for worker in self.workers:
                        worker.fit_distribute_split_info(class_idx, dep, best_splits)
                for worker in self.workers:
                    # ??????????????????bid??????????????????
                    worker.fit_convert(class_idx)
                # TODO
                # update feature importance
                # for worker in self.workers:
                #     worker.fit_update_feature_importance()

                # update predict score
                for worker in self.workers:
                    worker.fit_update_y_hat(class_idx, self.learning_rate, epoch_idx)
                    worker.update_feature_importance()
                    # self.tree_list.append(worker.fit_send_tree_list())

            # loss compute
            # local_loss = self.compute_loss(self.y_hat, self.y)
            # self.aggregator.send_local_loss(local_loss, self.data_bin.count(), suffix=(epoch_idx,))
        # print summary
        # self.set_summary(self.generate_summary())

    def predict_data(self, data):
        return self.workers[0].predict(data, self.learning_rate, self.boosting_round)
